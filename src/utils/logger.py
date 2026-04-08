import logging, json, uuid

def get_logger(name:str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger

def log_event(logger, event:str, trace_id:str, **kwargs):
    "Structured log with trace ID and arbitrary fields."
    payload = {
        "event" : event,
        "trace_id" : trace_id
        *kwargs
    }
    logger.info(json.dumps(payload))

def generate_trace_id()->str:
    return str(uuid.uuid4())[:8]