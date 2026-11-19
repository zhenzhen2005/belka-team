"""Bedrock access test: prints READY when your AWS sign-in and model access work."""
import boto3

# Your team account only allows calls in ap-southeast-1, ap-southeast-7 and us-east-1.
# Inference profiles that start with global. or apac. route to other Regions and are refused there,
# so this uses a model that runs in Singapore itself.
client = boto3.client("bedrock-runtime", region_name="ap-southeast-1")
reply = client.converse(
    modelId="anthropic.claude-sonnet-5",
    messages=[{"role": "user", "content": [{"text": "Reply with the word READY only."}]}],
    inferenceConfig={"maxTokens": 10},
)
print(reply["output"]["message"]["content"][0]["text"])
