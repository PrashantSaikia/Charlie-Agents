import os
import time
import concurrent.futures
from tools import get_relevant_documents, confluence_search, convert_to_jql, router_agent, query_confluence

def process_documents(query, documents, webui_links):
    context = ''
    relevant_webui_links = []
    timings = []

    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(check_document_relevance, i, query, documents[i], webui_links[i])
            for i in range(len(documents))
        ]
        for future in concurrent.futures.as_completed(futures):
            i, is_relevant, document, webui_link, elapsed_time = future.result()
            timings.append(elapsed_time)
            if is_relevant:
                context += document + '\n\n'
                relevant_webui_links.append(webui_link)

    total_processing_time = time.time() - start_time

    return context, relevant_webui_links, timings, total_processing_time

# Function to check document relevance
def check_document_relevance(i, query, document, webui_link):
    start_time = time.time()
    is_relevant = '1' in get_relevant_documents(query, document)
    elapsed_time = time.time() - start_time
    return i, is_relevant, document, webui_link, elapsed_time

def main_workflow(query):
    from tools import router_agent, query_confluence, confluence_search, get_relevant_documents, query_jira

    # Get the router to redirect to the appropriate function
    route_layer = router_agent(query)
    print(f"Router Output: {route_layer}")  # Debugging line

    if "confluence" in route_layer.lower():
        # Get the Confluence docs
        t = time.time()
        documents, webui_links = confluence_search(query)
        print(f'Time taken to do CQL search: {time.time() - t}s')

        # Process documents with multithreading
        context, relevant_webui_links, timings, total_processing_time = process_documents(query, documents, webui_links)
        print(f'Total time for document processing: {total_processing_time} seconds')
        print(f'Individual document processing times: {timings}')

        # If no relevant sources are found, respond with a disclaimer
        if len(relevant_webui_links) < 1:
            sentence = """There are no publicly available Confluence documents that I have access to with the knowledge 
            required to answer this question. However, I will try to answer your question with the knowledge I already have.
            \n\n
            **DISCLAIMER: Please note that the answer may not be accurate, so please verify the facts presented in this answer
            externally and DO NOT take them at face value.**
            \n\n
            """
            print(sentence)

        else:
            message = ""

            # # Get the LLM response
            # token_generator = query_confluence(context, query)
            # print(f'Time taken to generate the response with Solar: {time.time() - t}')
            
            # # Collect the LLM response
            # for token in token_generator:
            #     message += token

            message = query_confluence(context, query)

            # Construct the sources from the metadata
            sources = '\n\nSOURCES:\n'
            for i, link in enumerate(relevant_webui_links):
                sources += f'{i + 1}. {link}'

            if len(relevant_webui_links) >= 1:
                # Append the sources to the final message
                # message += sources
                print(sources)  # Display the final message with sources appended

    elif "jira" in route_layer.lower():
        message = query_jira(query)

if __name__=="__main__":
    user_query = input("Ask your question: ")
    main_workflow(user_query)
