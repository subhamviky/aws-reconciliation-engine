#List apprehensions
payments = [
    {"id": "1", "amount": 1500, "status": "PENDING"},
    {"id": "2", "amount": 2500, "status": "SETTLED"},
    {"id": "3", "amount": 500, "status": "PENDING"}
]

#Filter pending payments
pending = [p for p in payments if p["status"] == "PENDING"]
print(f"Pending : {pending}")

#Extract amounts
amounts = [p["amount"] for p in payments]
print(f"Amount : {amounts}")

#Total
total = sum(p["amount"] for p in payments)
print(f"Total : {total}")

#Decorator Example
import functools
import time

def log_execution(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        start = time.time()
        result = func(*args, *kwargs)
        print(f"{ func.__name__ } took { time.time() - start:.3f }s")
        return result
    return wrapper

@log_execution
def process_payment(payment_id: str):
    time.sleep(0.1) #simulate work
    return {"payment_id" : payment_id, "status": "PROCESSED"}

result = process_payment("PAY-001")
print(result)

