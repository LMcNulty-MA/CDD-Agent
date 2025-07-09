import logging

from app.config import settings
from app.core.documentdb import DocumentDBClient, MongoDBClient
from app.core.sso import SSOHandler

logger = logging.getLogger(__name__)

class DynamicConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DynamicConfigManager, cls).__new__(cls)
            cls._instance._config_cache = None
        return cls._instance

    def load_config(self):
        """
        Loads and caches the configuration data.
        """
        if self._config_cache is None:
            self._config_cache = self._retrieve_config_from_source()
        return self._config_cache

    def _retrieve_config_from_source(self):
        """
        Retrieves configuration data from the source.
        First tries direct MongoDB connection, then falls back to SSO-based DocumentDB API.
        """
        # Method 1: Try direct MongoDB connection first
        if settings.DOCDB_URI:
            try:
                # logger.info("Attempting direct MongoDB connection for config retrieval")
                # print(f"MongoDB URI: {settings.DOCDB_URI}")
                # print(f"Database: {settings.DOCDB_DATABASE_NAME}")
                # print(f"Collection: {settings.DOCUMENTDB_CONFIG_COLLECTION}")
                
                mongo_client = MongoDBClient(settings.DOCDB_URI, settings.DOCDB_DATABASE_NAME)
                
                # Query for cdd-agent configuration
                query_filter = {"product": "cdd-agent"}
                config_docs = mongo_client.get_documents(
                    collection_name=settings.DOCUMENTDB_CONFIG_COLLECTION,
                    query=query_filter,
                    limit=1
                )
                
                if config_docs and len(config_docs) > 0:
                    config = config_docs[0]
                    # Remove MongoDB internal fields
                    dynamic_settings = {k: v for k, v in config.items() if not k.startswith('_')}
                    logger.info("Successfully retrieved config via direct MongoDB connection")
                    return dynamic_settings
                else:
                    logger.warning("No config documents found for product 'cdd-agent'")
                    
            except Exception as e:
                logger.error(f"Direct MongoDB connection failed: {e}")
                logger.info("Falling back to SSO-based DocumentDB API")
        else:
            print("No MongoDB URI provided")
            raise Exception("No MongoDB URI provided")
        
        # # Method 2: Fallback to SSO-based DocumentDB API
        # try:
        #     logger.info("Attempting SSO-based DocumentDB API for config retrieval")
        #     print("Using SSO approach...")
        #     print(f"SSO Service URL: {settings.GLOBAL_SSO_SERVICE_URL}")
        #     print(f"DocumentDB Service URL: {settings.GLOBAL_DOCDB_SERVICE_URL}")
        #     print(f"Config Database: {settings.DOCUMENTDB_CONFIG_DATABASE}")
        #     print(f"Config Collection: {settings.DOCUMENTDB_CONFIG_COLLECTION}")

        #     sso_client = SSOHandler(sso_url=settings.GLOBAL_SSO_SERVICE_URL)

        #     document_db_client = DocumentDBClient(
        #         base_url=settings.GLOBAL_DOCDB_SERVICE_URL,
        #         database=settings.DOCUMENTDB_CONFIG_DATABASE or settings.DOCDB_DATABASE_NAME,
        #         collection=settings.DOCUMENTDB_CONFIG_COLLECTION
        #     )
        #     sso_token = sso_client.get_sso_token(sso_id=settings.SSO_SERVICE_ID, sso_secret=settings.SSO_SERVICE_SECRET)
        #     print(f"SSO Token: {sso_token}")
        #     filter_params = '{"product":"cdd-agent"}'

        #     config_data = document_db_client.get_documents(token=sso_token, filter_params=filter_params)
        #     print(f'Config data: {config_data}')
        #     dynamic_settings = document_db_client.parse_document(config_data)
        #     logger.info("Successfully retrieved config via SSO-based DocumentDB API")
        #     print(f"Config loaded via SSO: {dynamic_settings}")
        #     return dynamic_settings
        # except Exception as e:
        #     logger.error(f"SSO-based DocumentDB API also failed: {e}")
        #     logger.error("All configuration retrieval methods failed. The service will retry upon the next API call.")
        #     return None

    def get_config(self, key, default=None):
        """
        Retrieves a specific configuration by key.
        """
        config = self.load_config()
        if config:
            return config.get(key, default)
