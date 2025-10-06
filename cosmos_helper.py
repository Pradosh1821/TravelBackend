# cosmos_helper.py

import os
from azure.cosmos import CosmosClient, PartitionKey
from dotenv import load_dotenv
load_dotenv()
COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_KEY")
DATABASE_NAME = os.getenv("COSMOS_DATABASE", "TravelDB")
CONTAINER_NAME = os.getenv("COSMOS_CONTAINER", "Recommendations")

if not COSMOS_ENDPOINT or not COSMOS_KEY:
    raise ValueError("COSMOS_ENDPOINT and COSMOS_KEY must be set in your .env")

# Create client, database and container (idempotent)
client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
database = client.create_database_if_not_exists(id=DATABASE_NAME)
container = database.create_container_if_not_exists(
    id=CONTAINER_NAME,
    partition_key=PartitionKey(path="/session_id"),
    offer_throughput=400
)
def save_result(final_result: dict):
    """
    Upsert the entire final_result JSON (persona, recommendations, inter_city_travel, etc.)
    """
    return container.upsert_item(final_result)

def get_result(session_id: str):
    """
    Try to read item by id/partition_key; fallback to query if necessary.
    """
    try:
        return container.read_item(item=session_id, partition_key=session_id)
    except Exception:
        query = "SELECT * FROM c WHERE c.session_id=@session_id"
        items = list(container.query_items(
            query,
            parameters=[{"name": "@session_id", "value": session_id}],
            enable_cross_partition_query=True
        ))
        return items[0] if items else None
 