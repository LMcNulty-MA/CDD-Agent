import json
import logging
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

# In house imports
from app.config import settings
from app.core.dynamic_config_manager import DynamicConfigManager

logger = logging.getLogger(__name__)
dynamic_config_manager = DynamicConfigManager()

class ChatOpenAI(AzureChatOpenAI):
    def __init__(
        self,
        model,
        temperature=0,
        frequency_penalty=None,
        presence_penalty=None,
        top_p=None,
        model_kwargs=None,
    ):
        if model_kwargs is None:
            model_kwargs = {}
        
        azure_deployments = dynamic_config_manager.get_config('azure_ai_endpoints')

        if not azure_deployments:
            raise ValueError("Azure AI endpoints configuration is missing or empty. Ensure the dynamic configuration is set correctly.")

        try:
            if isinstance(azure_deployments, str):
                azure_deployments = json.loads(azure_deployments)  # Parse JSON string into a dictionary
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format for 'azure_ai_endpoints': {e}")

        azure_config = azure_deployments.get(settings.AZURE_DEPLOYMENT_API) if azure_deployments else None

        if not azure_config:
            raise ValueError("Azure AI endpoints configuration is missing.")

        if model not in azure_config:
            raise ValueError(f"Model {model} not supported by this Azure endpoint.")

        deployment_name = azure_config[model].get("deployment_name", None)
        api_version = azure_config[model].get("model_version", None)

        if not deployment_name or not api_version:
            raise ValueError(f"Required keys missing for model {model}: deployment_name or model_version")

        # We assume that model_kwargs should be empty, and that langchain is moving parametersto model_kwargs
        # When not supported by the current model. So we are cleaning the model_kwargs. But we log values "frequency_penalty", "presence_penalty", "top_p" and "seed" for debugging purposes
        for key in ["frequency_penalty", "presence_penalty", "top_p", "seed"]:
            if key in model_kwargs:
                logger.warning(f"Parameter {key} is not supported by model {model}")
                logger.warning(f"Value of {key} is {model_kwargs[key]}")
                model_kwargs.pop(key)

        
        # # Print all settings going into AzureChatOpenAI
        # settings_dict = {
        #     "azure_endpoint": settings.AZURE_DEPLOYMENT_API,
        #     "openai_api_version": api_version,
        #     "model_name": deployment_name,
        #     "deployment_name": deployment_name,
        #     "openai_api_key": f"{settings.AZURE_OPENAI_API_KEY[:5]}...{settings.AZURE_OPENAI_API_KEY[-5:] if len(settings.AZURE_OPENAI_API_KEY) > 10 else ''}",
        #     "openai_api_type": "azure",
        #     "temperature": temperature,
        #     "frequency_penalty": frequency_penalty,
        #     "presence_penalty": presence_penalty,
        #     "top_p": top_p,
        #     "model_kwargs": model_kwargs,
        # }
        # print("AzureChatOpenAI initialization settings:", json.dumps(settings_dict, indent=2, default=str))

        AzureChatOpenAI.__init__(
            self,
            azure_endpoint=settings.AZURE_DEPLOYMENT_API,
            openai_api_version=api_version,
            model_name=deployment_name,
            deployment_name=deployment_name,
            openai_api_key=settings.AZURE_OPENAI_API_KEY,
            openai_api_type="azure",
            temperature=temperature,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            top_p=top_p,
            model_kwargs=model_kwargs,
        )


class OpenAIEmbeddings(AzureOpenAIEmbeddings):
    def __init__(self, model):
        azure_deployments = dynamic_config_manager.get_config('azure_ai_endpoints')
        
        if not azure_deployments:
            raise ValueError("Azure AI endpoints configuration is missing or empty. Ensure the dynamic configuration is set correctly.")

        try:
            if isinstance(azure_deployments, str):
                azure_deployments = json.loads(azure_deployments)  # Parse JSON string into a dictionary
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format for 'azure_ai_endpoints': {e}")

        azure_config = azure_deployments.get(settings.AZURE_DEPLOYMENT_API)
        if not azure_config:
            raise ValueError("Azure AI endpoints configuration is missing.")

        if model not in azure_config:
            raise ValueError(f"Model {model} not supported by this Azure endpoint.")

        deployment_name = azure_config[model].get("deployment_name", None)
        api_version = azure_config[model].get("model_version", None)

        if not deployment_name or not api_version:
            raise ValueError(f"Required keys missing for model {model}: deployment_name or model_version")
        
        AzureOpenAIEmbeddings.__init__(
            self,
            azure_endpoint=settings.AZURE_DEPLOYMENT_API,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=api_version,
            azure_deployment=deployment_name,
            model=model,
        )
