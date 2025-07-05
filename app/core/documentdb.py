import requests
import logging
import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from typing import List, Dict

logger = logging.getLogger(__name__)

# Global shared client instance to prevent connection overhead
_shared_client = None

# --- DocumentDB API Client (using SSO Token) ---
class DocumentDBClient:
    def __init__(self, base_url: str, database: str, collection: str):
        self.base_url = base_url.rstrip('/')
        self.database = database
        self.collection = collection

    def get_documents(self, token: str, filter_params: str, limit: int = 20, offset: int = 1) -> dict:
        url = f"{self.base_url}/v1/databases/{self.database}/collections/{self.collection}"
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {token}',
            'referer': 'https://rafa.moodysanalytics.com'
        }
        params = {'filter': filter_params, 'limit': limit, 'offset': offset}
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"DocumentDB GET failed: {e}")
            logger.error(f"Response body: {e.response.text if e.response else 'No response'}")
            raise

    def delete_documents(self, token: str, filter_params: dict) -> dict:
        url = f"{self.base_url}/v1/databases/{self.database}/collections/{self.collection}/documents"
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {token}',
            'referer': 'https://rafa.moodysanalytics.com'
        }
        try:
            response = requests.delete(url, headers=headers, json=filter_params)
            response.raise_for_status()
            logger.info(f"Deleted documents matching {filter_params} from '{self.collection}'")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"DocumentDB DELETE failed: {e}")
            logger.error(f"Response body: {e.response.text if e.response else 'No response'}")
            raise

    def insert_documents(self, token: str, documents: list) -> dict:
        url = f"{self.base_url}/v1/databases/{self.database}/collections/{self.collection}/documents"
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'referer': 'https://rafa.moodysanalytics.com'
        }
        try:
            response = requests.post(url, headers=headers, json=documents)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"DocumentDB POST failed: {e}")
            logger.error(f"Response body: {e.response.text if e.response else 'No response'}")
            raise

    def create_index(self, token: str, field: str = None, unique: bool = False) -> dict:
        if not field:
            raise ValueError("Field name must be provided for index creation.")
        index_spec = {"key": {field: 1}, "name": f"{field}_index", "unique": unique}
        url = f"{self.base_url}/v1/databases/{self.database}/collections/{self.collection}/indexes"
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'referer': 'https://rafa.moodysanalytics.com'
        }
        try:
            response = requests.post(url, headers=headers, json=index_spec)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Index creation failed: {e}")
            logger.error(f"Response body: {e.response.text if e.response else 'No response'}")
            raise

    def drop_collection(self, token: str) -> None:
        url = f"{self.base_url}/v1/databases/{self.database}/collections/{self.collection}"
        headers = {
            'accept': '*/*',
            'Authorization': f'Bearer {token}',
            'referer': 'https://rafa.moodysanalytics.com'
        }
        try:
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            logger.info(f"Dropped collection '{self.collection}'")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to drop collection '{self.collection}': {e}")
            logger.error(f"Response body: {e.response.text if e.response else 'No response'}")
            raise

    def test_connection(self, token: str) -> bool:
        try:
            self.drop_collection(token)
            test_document = [{"id": 1, "name": "Test", "value": "TestData"}]
            self.insert_documents(token, test_document)
            logger.info("Inserted test document into 'test_collection'")
            self.create_index(token, field="id", unique=True)
            logger.info("Created index on 'id' for 'test_collection'")
            result = self.get_documents(token, filter_params='{"id": 1}', limit=1)
            documents = result.get('data', [])
            if len(documents) == 1 and documents[0].get('name') == "Test":
                logger.info("Test passed: Document written and read successfully")
                return True
            else:
                logger.error(f"Test failed: Document not found or incorrect. Expected 1 document with name 'Test', got: {len(documents)}")
                return False
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return False

    @staticmethod
    def parse_document(data: dict) -> dict:
        if 'data' in data and len(data['data']) > 0:
            config = data['data'][0]
            return {k: v for k, v in config.items() if not k.startswith('_')}
        return None

# --- Async MongoDB Client (using motor) ---
class AsyncMongoDBClient:
    def __init__(self, uri: str, database: str):
        self.uri = uri
        self.database = database
        # Add connection timeout and other options for better reliability
        self.client = AsyncIOMotorClient(
            self.uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            retryWrites=True
        )
        self.db = self.client[database]

    @classmethod
    def get_shared_client(cls, uri: str, database: str):
        """Get a shared client instance to reuse connections"""
        global _shared_client
        if _shared_client is None:
            _shared_client = cls(uri, database)
        return _shared_client

    async def insert_documents(self, collection_name: str, documents: List[Dict]) -> None:
        try:
            collection = self.db[collection_name]
            if documents:
                await collection.insert_many(documents)
        except Exception as e:
            logger.error(f"Async MongoDB insert failed: {e}")
            raise

    async def create_index(self, collection_name: str, field: str, unique: bool = False) -> None:
        try:
            collection = self.db[collection_name]
            await collection.create_index([(field, pymongo.ASCENDING)], unique=unique, name=f"{field}_index")
        except Exception as e:
            logger.error(f"Async MongoDB index creation failed: {e}")
            raise

    async def get_documents(self, collection_name: str, query: Dict, limit: int = 1) -> List[Dict]:
        try:
            collection = self.db[collection_name]
            cursor = collection.find(query).limit(limit)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Async MongoDB get documents failed: {e}")
            raise

    async def find_all(
        self,
        collection_name: str,
        query: Dict = None,
        projection: Dict = None,
        limit: int = 0,
        skip: int = 0
    ) -> List[Dict]:
        """
        Retrieves documents from the specified collection with optional query, projection, and pagination.

        Args:
            collection_name (str): Name of the collection to query.
            query (Dict, optional): MongoDB query filter (e.g., {"fed_rssd": 599643}).
            projection (Dict, optional): Fields to include/exclude (e.g., {"_id": 0}).
            limit (int, optional): Maximum number of documents to return (0 for no limit).
            skip (int, optional): Number of documents to skip.

        Returns:
            List[Dict]: List of documents matching the query.
        """
        try:
            collection = self.db[collection_name]
            cursor = collection.find(query or {}, projection)
            if skip > 0:
                cursor = cursor.skip(skip)
            if limit > 0:
                cursor = cursor.limit(limit)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Async MongoDB find all failed: {e}")
            raise

    async def aggregate(self, collection_name: str, pipeline: List[Dict]) -> List[Dict]:
        """
        Executes an aggregation pipeline on the specified collection.

        Args:
            collection_name (str): Name of the collection to aggregate.
            pipeline (List[Dict]): MongoDB aggregation pipeline stages.

        Returns:
            List[Dict]: List of documents resulting from the aggregation.

        Example:
            pipeline = [
                {"$match": {"asset": {"$gt": 100000}}},
                {"$project": {"_id": 0, "fed_rssd": 1, "name": 1}}
            ]
        """
        try:
            collection = self.db[collection_name]
            cursor = collection.aggregate(pipeline)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Async MongoDB aggregation failed: {e}")
            raise

    async def delete_documents(self, collection_name: str, query: Dict) -> None:
        try:
            collection = self.db[collection_name]
            result = await collection.delete_many(query)
            logger.info(f"Deleted {result.deleted_count} documents from '{collection_name}'")
        except Exception as e:
            logger.error(f"Async MongoDB delete failed: {e}")
            raise

    async def drop_collection(self, collection_name: str) -> None:
        try:
            collection = self.db[collection_name]
            await collection.drop()
            logger.info(f"Dropped collection '{collection_name}'")
        except Exception as e:
            logger.error(f"Failed to drop collection '{collection_name}': {e}")
            raise

    async def test_connection(self) -> bool:
        try:
            collection = self.db['test_collection']
            await collection.drop()
            test_document = [{"id": 1, "name": "Test", "value": "TestData"}]
            await collection.insert_many(test_document)
            logger.info("Inserted test document into 'test_collection'")
            await collection.create_index([("id", pymongo.ASCENDING)], unique=True, name="id_index")
            logger.info("Created index on 'id' for 'test_collection'")
            cursor = collection.find({"id": 1}).limit(1)
            documents = [doc async for doc in cursor]
            if len(documents) == 1 and documents[0].get('name') == "Test":
                logger.info("Test passed: Document written and read successfully")
                return True
            else:
                logger.error(f"Test failed: Document not found or incorrect. Expected 1 document with name 'Test', got: {len(documents)}")
                return False
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return False

# Retain the synchronous MongoDBClient for backward compatibility
class MongoDBClient:
    def __init__(self, uri: str, database: str):
        self.uri = uri
        self.database = database

    def insert_documents(self, collection_name: str, documents: List[Dict]) -> None:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                collection = db[collection_name]
                if documents:
                    collection.insert_many(documents)
        except PyMongoError as e:
            logger.error(f"MongoDB insert failed: {e}")
            raise

    def create_index(self, collection_name: str, field: str, unique: bool = False) -> None:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                collection = db[collection_name]
                collection.create_index([(field, pymongo.ASCENDING)], unique=unique, name=f"{field}_index")
        except PyMongoError as e:
            logger.error(f"MongoDB index creation failed: {e}")
            raise

    def get_documents(self, collection_name: str, query: Dict, limit: int = 1) -> List[Dict]:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                collection = db[collection_name]
                return list(collection.find(query).limit(limit))
        except PyMongoError as e:
            logger.error(f"MongoDB get documents failed: {e}")
            raise

    def update_document(self, collection_name: str, query: Dict, update: Dict) -> None:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                collection = db[collection_name]
                result = collection.update_one(query, update)
                logger.info(f"Updated {result.modified_count} document(s) in '{collection_name}'")
        except PyMongoError as e:
            logger.error(f"MongoDB update failed: {e}")
            raise

    def delete_documents(self, collection_name: str, query: Dict) -> None:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                collection = db[collection_name]
                result = collection.delete_many(query)
                logger.info(f"Deleted {result.deleted_count} documents from '{collection_name}'")
        except PyMongoError as e:
            logger.error(f"MongoDB delete failed: {e}")
            raise

    def drop_collection(self, collection_name: str) -> None:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                db[collection_name].drop()
                logger.info(f"Dropped collection '{collection_name}'")
        except PyMongoError as e:
            logger.error(f"Failed to drop collection '{collection_name}': {e}")
            raise

    def test_connection(self) -> bool:
        try:
            with pymongo.MongoClient(self.uri) as client:
                db = client[self.database]
                collection = db['test_collection']
                collection.drop()
                test_document = [{"id": 1, "name": "Test", "value": "TestData"}]
                collection.insert_many(test_document)
                logger.info("Inserted test document into 'test_collection'")
                collection.create_index([("id", pymongo.ASCENDING)], unique=True, name="id_index")
                logger.info("Created index on 'id' for 'test_collection'")
                result = collection.find({"id": 1}).limit(1)
                documents = list(result)
                if len(documents) == 1 and documents[0].get('name') == "Test":
                    logger.info("Test passed: Document written and read successfully")
                    return True
                else:
                    logger.error(f"Test failed: Document not found or incorrect. Expected 1 document with name 'Test', got: {len(documents)}")
                    return False
        except PyMongoError as e:
            logger.error(f"Test failed: {e}")
            return False 