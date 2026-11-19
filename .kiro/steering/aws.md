---
inclusion: always
---
# Working with AWS

- Use the AWS MCP server for every AWS question or action. Do not answer from memory.
- Before an AWS task, look for a relevant skill. Load it with `aws___retrieve_skill` and follow it over general knowledge.
  The server provides the skills; there is nothing to install.
- If you are unsure about an API parameter, permission or limit, check the current documentation first.
- Prefer infrastructure as code (CDK or CloudFormation) over one-off CLI commands.
- Our region is ap-southeast-1. List and describe before you create.
- The team account refuses calls outside ap-southeast-1, ap-southeast-7 and us-east-1. For Amazon Bedrock use
  `anthropic.claude-sonnet-5` in ap-southeast-1. Never use model IDs that start with `global.` or `apac.`: they route
  to other Regions and are refused. This also applies to code the AgentCore CLI generates.
- Never delete or change anything in the team account without asking.
- The AgentCore CLI is pinned at 0.30.0 (code agents, CodeZip). Do not install `@latest` or `@preview`, and do not switch to
  Harness commands, unless asked. If a skill says otherwise, tell me and wait.
