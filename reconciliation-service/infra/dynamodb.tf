# Reconciliation state: one DynamoDB table, single-table design (pk / sk), as used by
# src/reconciliation_service/services/repository.py. Added by hand next to the
# A2C-generated main.tf, which stays untouched apart from the Lambda environment.

variable "table_name_suffix" {
  type        = string
  description = "Suffix of the reconciliation table name."
  default     = "state"
}

resource "aws_dynamodb_table" "recon" {
  name         = "${local.name}-${var.table_name_suffix}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = local.tags
}

# Least privilege: item-level reads/writes and transactions on this table only.
data "aws_iam_policy_document" "table" {
  statement {
    sid = "ReconciliationTable"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.recon.arn]
  }
}

resource "aws_iam_role_policy" "table" {
  name   = "${local.name}-table"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.table.json
}

output "table_name" {
  value = aws_dynamodb_table.recon.name
}
