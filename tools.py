from jira import JIRA
import boto3, json, os
from io import StringIO
from ollama import Client
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
import requests, json, os, time
from requests.auth import HTTPBasicAuth

load_dotenv()

# Set up the Ollama client
OLLAMA_API_ENDPOINT = os.getenv('OLLAMA_API_ENDPOINT')
ollama_client = Client(host=OLLAMA_API_ENDPOINT)
model = 'kristada673/solar-10.7b-instruct-v1.0-uncensored'

# Confluence credentials
base_url = 'https://input-output.atlassian.net/wiki/rest/api'
username = 'prasanta.saika@iohk.io'
CONFLUENCE_API_TOKEN = os.getenv('CONFLUENCE_API_TOKEN')

# Jira credentials
jira_server = 'https://input-output.atlassian.net'
jira_options = {'server': jira_server}
username = 'prasanta.saika@iohk.io'
jira = JIRA(options=jira_options, basic_auth=(username, CONFLUENCE_API_TOKEN))

# Bedrock credentials
aws_access_key_id = os.getenv('aws_access_key_id')
aws_secret_access_key = os.getenv('aws_secret_access_key')

def get_relevant_documents(query, document):

    # Make the document fit within the context window of llama3
    if len(document)>8000:
        document = document[0:8000]

    # Prompt
    prompt = f"""<|begin_of_text|>
    <|start_header_id|>user<|end_header_id|>
    You are a professional researcher.

    You will be given a user query and a text document. The user wants to know whether they can read that document and get 
    an answer to their query. Your goal is to help the user with that and say whether the document is highly relevant to 
    answering the query. If the document merely mentions words in the query, you should count is as not relevant. Only if the
    document contains subsantial information pertaining to the query you should consider it as relevant.
    
    Here is the document:
    {document}
    
    Here is the user query: 
    {query}

    Simply answer 0 if the document is not relevant to the query, and 1 if the document is relevant to the query.
    <|eot_id|>
    <|start_header_id|>assistant<|end_header_id|>
    """

    bedrock=boto3.client(service_name="bedrock-runtime", 
                         region_name="us-west-2",
                         aws_access_key_id=aws_access_key_id,
                         aws_secret_access_key=aws_secret_access_key
                        )
    
    payload={
        "prompt": prompt, 
        "max_gen_len":8,
        "temperature":0,
        "top_p":0.1
    }
    body=json.dumps(payload)
    model_id="meta.llama3-70b-instruct-v1:0"

    response=bedrock.invoke_model(
        body=body,
        modelId=model_id,
        accept="application/json",
        contentType="application/json"
    )
    
    response_body=json.loads(response.get("body").read())
    repsonse_text=response_body['generation']
    return repsonse_text

def confluence_search(search_term):
    '''
    INPUT: a search term
    OUTPUT: a list of confluence documents for the search term

    We do the following:
    - extract the named entities from the search term (otherwise it sometimes returns blank results for the full search query)
    - a CQL (confluence query language) search on the search term
    - get the content IDs returned for the search term
    - read the content of the confluence docs for those content IDs
    - extract the HTML content and convert it to text.
    '''

    # Remove double quotes and leading and trailing whitespaces from the serach term
    search_term = search_term.replace('"', '').strip()
    
    # CQL search query
    query = f'siteSearch ~ "{search_term}"' #  order by lastmodified desc'  # trunc_query
    # query = f'title ~ "{trunc_query}"'
    
    # API endpoint for search
    search_url = f'{base_url}/content/search'
    
    # Headers and authentication
    headers = {
        'Accept': 'application/json'
    }
    auth = (username, CONFLUENCE_API_TOKEN)
    
    # Parameters for the search query
    params = {
        'cql': query,
        'limit': 5  # Limit to 10 search results
    }
    
    # Send the search request
    response = requests.get(search_url, headers=headers, auth=auth, params=params)
    
    # Check for successful search response
    if response.status_code == 200:
        search_results = response.json()
        
        # Extract content IDs from search results
        content_ids = [result['id'] for result in search_results['results']]

        # List to contain the retrieved confluence documents
        documents = []
        webui_links = []
        
        # Function to get content details
        def get_content_details(content_id):
            content_url = f'{base_url}/content/{content_id}?expand=body.view,version,history'
            content_response = requests.get(content_url, headers=headers, auth=auth)
            
            if content_response.status_code == 200:
                content_details = content_response.json()
                content_data = {
                    'content': content_details['body']['view']['value'],
                    'created_date': content_details['history']['createdDate'],
                    'last_modified_date': content_details['version']['when'],
                    'webui_link': content_details['_links']['webui']
                }
                return content_data
            else:
                print(f'Failed to retrieve content {content_id}: {content_response.status_code} - {content_response.text}')
                return None
        
        # Retrieve and print content details for each content ID
        for content_id in content_ids:
            content_details = get_content_details(content_id)
            if content_details:
                text = BeautifulSoup(content_details['content'], features="lxml").get_text().replace('\xa0', '\n')
                documents.append(text)
                webui_links.append(base_url.split('/rest/api')[0] + content_details["webui_link"])
                
        return documents, webui_links
        
    else:
        print(f'Failed to retrieve search results: {response.status_code} - {response.text}')

def query_confluence(context, query):
    # Append the context to the prompt
    prompt = f"""<s>[INST]You are a professional assistant that provides accurate information about any project or 
    specific employee's work when asked.

    The questions are generally about what's going on in a certain project, or to summarize or describe something. 
    The context that is provided to you is the information where you will find the answer to the question.
    
    Here is the context:
    {context}
    
    Here is the user query: 
    {query}

    Answer the question professionally, with bullet points to elaborate each point if needed. Directly start answering the question based 
    on the facts you learned from the context provided, no need to begin your response with "Based on the context provided".

    If you can't answer the question based on the context provided to you, say "I don't know"[/INST].
    """
    
    bedrock=boto3.client(service_name="bedrock-runtime", 
                         region_name="us-west-2",
                         aws_access_key_id=aws_access_key_id,
                         aws_secret_access_key=aws_secret_access_key
                        )
    
    payload={
        "prompt": prompt, 
        "max_tokens":4000,
        "temperature":0.1,
        "top_p":0.2
    }
    body=json.dumps(payload)
    model_id="mistral.mixtral-8x7b-instruct-v0:1"

    response=bedrock.invoke_model_with_response_stream(  ## invoke_model
        body=body,
        modelId=model_id,
        accept="application/json",
        contentType="application/json"
    )

    # Extract and print the response text in real-time.
    first_token = 1
    t = time.time()
    for event in response["body"]:
        chunk = json.loads(event["chunk"]["bytes"])
        if first_token:
            print(f'\nTime taken to do generate first token by LLM: {time.time() - t}s\n')
            first_token = 0
        if "outputs" in chunk:
            print(chunk["outputs"][0].get("text"), end="")

def convert_to_jql(user_query):
    """
    This function takes a user query, processes it using the Llama3-70B model,
    queries the Jira server, and returns the response.

    Parameters:
    user_query (str): The query input from the user.

    Returns:
    dict: The response containing the list of issues.
    """
    try:
        # Prompt
        prompt = f"""<|begin_of_text|>
        <|start_header_id|>user<|end_header_id|>

        You are a professional JQL (Jira Query Language) expert. 
        
        Convert the following natural language query into a JQL statement: {user_query}

        Only respond with the JQL statement, and no verbose talk.
        
        <|eot_id|>
        <|start_header_id|>assistant<|end_header_id|>
        """
    
        bedrock=boto3.client(service_name="bedrock-runtime", 
                             region_name="us-west-2",
                             aws_access_key_id=aws_access_key_id,
                             aws_secret_access_key=aws_secret_access_key
                            )
        
        payload={
            "prompt": prompt, 
            "max_gen_len":100,
            "temperature":0,
            "top_p":0.1
        }
        body=json.dumps(payload)
        model_id="meta.llama3-70b-instruct-v1:0"
    
        response=bedrock.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body=json.loads(response.get("body").read())
        jql_query = response_body['generation']
        # print(f'The JQL query is: {jql_query}\n\n')

        # Use Jira API to query the information
        issues = jira.search_issues(jql_query)

        # Format the response
        issues_list = []
        for issue in issues:
            issues_list.append({
                'key': issue.key,
                'summary': issue.fields.summary,
                'status': issue.fields.status.name,
                'created': datetime.strptime(issue.fields.created, '%Y-%m-%dT%H:%M:%S.%f%z').strftime('%d-%m-%Y %I:%M %p'),
                # 'updated': issue.fields.updated,
                # 'resolution_date': issue.fields.resolutiondate,
                'time_estimated_hours' : int(issue.fields.timeoriginalestimate) / 3600 if issue.fields.timeoriginalestimate is not None else None,
                'time_spent' : int(issue.fields.timespent) / 3600 if issue.fields.timespent is not None else None
            })

        return issues_list

    except Exception as e:
        # return {'error': str(e)}
        return '''No tasks found. Some possible reasons might be:
        - typo in the name of the person
        - they did not create any tasks in the specified time period
        - the JQL query constructed from the natural language query is incorrect
        '''


def query_jira(user_query):
    # Get the issues with JQL search
    issues_list = convert_to_jql(user_query)

    # Prompt
    prompt = f"""<s>[INST]
    You will be given a Python dictionary containing some tasks and related information. Your job is to write about each of the tasks
    in the following format:

    1. <summary>:
        - Key: <key>
        - Status: <status>
        - Created: <created>
        - Time Estimated (h): <time_estimated>
        - Time Spent (h): <time_spent>

    2. <summary>:
        - Key: <key>
        - Status: <status>
        - Created: <created>
        - Time Estimated: <time_estimated>
        - Time Spent: <time_spent>

        ...
        
    And so on for all the tasks in the dictionary.
    
    Here is the dictionary: {issues_list}

    Directly answer the question, no verbose talk.
    [/INST]
    """

    bedrock=boto3.client(service_name="bedrock-runtime", 
                         region_name="us-west-2",
                         aws_access_key_id=aws_access_key_id,
                         aws_secret_access_key=aws_secret_access_key
                        )
    
    payload={
        "prompt": prompt, 
        "max_tokens":4000,
        "temperature":0.1,
        "top_p":0.2
    }
    body=json.dumps(payload)
    model_id="mistral.mixtral-8x7b-instruct-v0:1"

    response=bedrock.invoke_model_with_response_stream(  ## invoke_model
        body=body,
        modelId=model_id,
        accept="application/json",
        contentType="application/json"
    )

    # Extract and print the response text in real-time.
    first_token = 1
    t = time.time()
    for event in response["body"]:
        chunk = json.loads(event["chunk"]["bytes"])
        if first_token:
            print(f'\nTime taken to do generate first token by LLM: {time.time() - t}s\n')
            first_token = 0
        if "outputs" in chunk:
            print(chunk["outputs"][0].get("text"), end="")


def router_agent(user_query):
    t = time.time()

    # Prompt
    prompt = f"""<|begin_of_text|>
    <|start_header_id|>user<|end_header_id|>
    You will be given a user query. Your job is to say is it a "confluence" query or a "jira" query.

    Here are some examples of confluence queries:

    - Describe the midnight architecture
    - What is the travel policy for trains in IOG?
    - What should new employees do when joining IOG?
    - Summarize the Babel innovation workstream

    Here are some examples of jira queries:

    - What is Hakan Tekbas working on?
    - What has Prasanta Saika worked on in the past week?
    - What is the status of Martin Ross' tasks?
    - What are Stefan Contiu's main tasks this month?
    
    Here is the user query: 
    {user_query}

    Simply answer "confluence" if it is a confluence query, or "jira" if it is a jira query.
    <|eot_id|>
    <|start_header_id|>assistant<|end_header_id|>
    """

    bedrock=boto3.client(service_name="bedrock-runtime", 
                         region_name="us-west-2",
                         aws_access_key_id=aws_access_key_id,
                         aws_secret_access_key=aws_secret_access_key
                        )
    
    payload={
        "prompt": prompt, 
        "max_gen_len":8,
        "temperature":0,
        "top_p":0.1
    }
    body=json.dumps(payload)
    model_id= "meta.llama3-8b-instruct-v1:0"

    response=bedrock.invoke_model(
        body=body,
        modelId=model_id,
        accept="application/json",
        contentType="application/json"
    )
    
    response_body=json.loads(response.get("body").read())
    response_text=response_body['generation']
    print(f'\nTime taken for the router agent: {time.time() - t}s\n')
    return response_text