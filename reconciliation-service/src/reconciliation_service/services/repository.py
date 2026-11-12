"""DynamoDB single-table repository. Every state change is a conditional write;
matching several open items is ONE transaction, so an item can never be matched
twice and a line is never half-matched (E2A: conditional commit, effectively-once
effects under at-least-once delivery).

Keys (pk / sk):
  OPEN#<tenant>#<account> / ITEM#<settlement_id>   open item (expected cash)
  LINE#<tenant>           / <line_id>              bank statement line
  EXC#<tenant>            / <line_id>              exception case
  CURSOR#<tenant>         / settlement-feed        position in the settlement event feed
"""
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from ..models.records import BankLine, ExceptionCase, OpenItem


def _conditional_failure(error: ClientError) -> bool:
    """True only for a lost condition (another writer got there first). Any other
    cancellation reason (validation, throughput, a bug) is raised, never hidden."""
    code = error.response["Error"]["Code"]
    if code == "ConditionalCheckFailedException":
        return True
    if code == "TransactionCanceledException":
        reasons = [r.get("Code") for r in error.response.get("CancellationReasons", [])]
        return "ConditionalCheckFailed" in reasons and all(r in ("ConditionalCheckFailed", "None", None)
                                                            for r in reasons)
    return False


class ReconRepository:
    def __init__(self, table) -> None:
        self.table = table                              # boto3 DynamoDB Table resource
        self.client = table.meta.client                 # the resource's client: plain Python values

    # ------------------------------------------------------------ open items
    def add_open_item(self, tenant: str, item: OpenItem) -> bool:
        """Idempotent: a settlement event delivered twice creates one open item."""
        try:
            self.table.put_item(
                Item={"pk": f"OPEN#{tenant}#{item.account}", "sk": f"ITEM#{item.settlement_id}",
                      **json.loads(item.model_dump_json())},
                ConditionExpression="attribute_not_exists(pk)")
            return True
        except ClientError as e:
            if _conditional_failure(e):
                return False
            raise

    def open_items(self, tenant: str, account: str, currency: str) -> List[OpenItem]:
        items = self._query(f"OPEN#{tenant}#{account}")
        return sorted((OpenItem.model_validate(i) for i in items
                       if i["status"] == "OPEN" and i["currency"] == currency),
                      key=lambda i: (i.settled_at, i.settlement_id))

    def get_open_item(self, tenant: str, account: str, settlement_id: str) -> Optional[OpenItem]:
        found = self.table.get_item(Key={"pk": f"OPEN#{tenant}#{account}", "sk": f"ITEM#{settlement_id}"}).get("Item")
        return OpenItem.model_validate(found) if found else None

    # ----------------------------------------------------------------- lines
    def add_line(self, tenant: str, line: BankLine) -> bool:
        """Idempotent ingestion: the same line_id is stored once."""
        try:
            self.table.put_item(Item={"pk": f"LINE#{tenant}", "sk": line.line_id, "status": "RECEIVED",
                                      **json.loads(line.model_dump_json())},
                                ConditionExpression="attribute_not_exists(pk)")
            return True
        except ClientError as e:
            if _conditional_failure(e):
                return False
            raise

    def get_line(self, tenant: str, line_id: str) -> Optional[Dict[str, Any]]:
        return self.table.get_item(Key={"pk": f"LINE#{tenant}", "sk": line_id}).get("Item")

    def lines(self, tenant: str) -> List[Dict[str, Any]]:
        return self._query(f"LINE#{tenant}")

    def set_line_status(self, tenant: str, line_id: str, status: str) -> None:
        self.table.update_item(Key={"pk": f"LINE#{tenant}", "sk": line_id},
                               UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"},
                               ExpressionAttributeValues={":s": status})

    def match(self, tenant: str, line: BankLine, items: List[OpenItem], match_type: str,
              write_off: Decimal = Decimal("0.00")) -> bool:
        """Match a line to one or more open items in ONE transaction. False when any
        item is no longer OPEN at its expected version, or the line is already matched."""
        actions = []
        for item in items:
            actions.append({"Update": {
                "TableName": self.table.name,
                "Key": {"pk": f"OPEN#{tenant}#{item.account}", "sk": f"ITEM#{item.settlement_id}"},
                "UpdateExpression": "SET #s = :matched, version = version + :one, matched_line = :line",
                "ConditionExpression": "#s = :open AND version = :v",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": ({":matched": "MATCHED", ":open": "OPEN", ":one": 1,
                                                     ":v": item.version, ":line": line.line_id}),
            }})
        actions.append({"Update": {
            "TableName": self.table.name,
            "Key": {"pk": f"LINE#{tenant}", "sk": line.line_id},
            "UpdateExpression": "SET #s = :matched, matched_settlements = :ids, match_type = :type, write_off = :wo",
            "ConditionExpression": "#s IN (:received, :exception)",
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": ({":matched": "MATCHED", ":received": "RECEIVED",
                                                 ":exception": "EXCEPTION", ":type": match_type,
                                                 ":ids": [i.settlement_id for i in items],
                                                 ":wo": str(write_off)}),
        }})
        try:
            self.client.transact_write_items(TransactItems=actions)
            return True
        except ClientError as e:
            if _conditional_failure(e):
                return False
            raise

    # ------------------------------------------------------------ exceptions
    def put_exception(self, tenant: str, case: ExceptionCase) -> None:
        self.table.put_item(Item={"pk": f"EXC#{tenant}", "sk": case.line_id, **json.loads(case.model_dump_json())})

    def get_exception(self, tenant: str, line_id: str) -> Optional[ExceptionCase]:
        found = self.table.get_item(Key={"pk": f"EXC#{tenant}", "sk": line_id}).get("Item")
        return ExceptionCase.model_validate(found) if found else None

    def exceptions(self, tenant: str) -> List[ExceptionCase]:
        return [ExceptionCase.model_validate(i) for i in self._query(f"EXC#{tenant}")]

    # ---------------------------------------------------------------- cursor
    def get_cursor(self, tenant: str) -> int:
        found = self.table.get_item(Key={"pk": f"CURSOR#{tenant}", "sk": "settlement-feed"}).get("Item")
        return int(found["position"]) if found else 0

    def advance_cursor(self, tenant: str, old: int, new: int) -> bool:
        """Moves forward only, and only from the position the caller read."""
        try:
            self.table.put_item(Item={"pk": f"CURSOR#{tenant}", "sk": "settlement-feed", "position": new},
                                ConditionExpression=Attr("pk").not_exists() | Attr("position").eq(old))
            return True
        except ClientError as e:
            if _conditional_failure(e):
                return False
            raise

    # --------------------------------------------------------------- helpers
    def _query(self, pk: str) -> List[Dict[str, Any]]:
        items, kwargs = [], {"KeyConditionExpression": Key("pk").eq(pk)}
        while True:
            page = self.table.query(**kwargs)
            items += page.get("Items", [])
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
