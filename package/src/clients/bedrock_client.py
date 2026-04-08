from langchain_aws.embeddings import BedrockEmbeddings

def get_bedrock_embeddings():
    return BedrockEmbeddings(
        model_id="amazon.titan-embed-text-v1"
        # region is inferred from AWS_DEFAULT_REGION
        # set: export AWS_DEFAULT_REGION=us-east-1
    )
