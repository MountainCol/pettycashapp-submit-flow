import logging
from mangum import Mangum

from pettycash.main import app

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create Mangum adapter with proper configuration for API Gateway
handler = Mangum(
    app,
    lifespan="off",
    api_gateway_base_path=None,  # Set to None for root path
    text_mime_types=[
        "application/json",
        "application/javascript",
        "application/xml",
        "application/vnd.api+json",
        "text/plain",
        "text/html",
        "text/css",
        "text/javascript",
        "text/xml",
    ]
)

def lambda_handler(event, context):
    """
    AWS Lambda handler function that processes API Gateway events.
    """
    try:
        logger.info(f"Received event: {event}")
        logger.info(f"Event type: {type(event)}")
        
        # Ensure event is a dictionary
        if not isinstance(event, dict):
            logger.error(f"Invalid event type: {type(event)}")
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": '{"error": "Invalid event format"}'
            }
        
        # Check if this is an API Gateway event
        if "httpMethod" in event or "requestContext" in event:
            logger.info("Processing API Gateway event")
            return handler(event, context)
        else:
            logger.error("Event does not appear to be from API Gateway")
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": '{"error": "Invalid event source"}'
            }
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": f'{{"error": "Internal server error: {str(e)}"}}'
        }
