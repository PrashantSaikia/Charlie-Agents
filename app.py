import panel as pn
from main import main_workflow

pn.extension()

# Initialize the chat history
chat_history = []

def callback(query: str, user: str, instance: pn.chat.ChatInterface):
    message = main_workflow(query)
    # Update the chat history with the LLM response
    chat_history.append({"role": "assistant", "content": message})

# Chat Interface setup
chat_interface = pn.chat.ChatInterface(
    callback=callback,
    callback_user="Charlie",
    sizing_mode="stretch_width",
    callback_exception='verbose',
    message_params=dict(
        default_avatars={"Charlie": "C", "User": "U"},
        reaction_icons={"like": "thumb-up"},
    ),
)

# Greeting message
chat_interface.send(
    {"object":"""<p id='first_prompt'>
    Hi, you can ask me about anything on IOG's Confluence and Jira.
    """
    },
    user = "Charlie",
    respond = False,
)

# Define adjustable settings
# system_prompt = pn.widgets.TextAreaInput(name='System Prompt', value="You are a helpful assistant. You respond to user queries with to-the-point answers based on the context provided to you. If the query cannot be answered based on the provided context, your answer should be 'I don't know'.", width=500, height=80)
top_k_slider = pn.widgets.FloatSlider(name='top-k', start=0.0, end=100.0, value=15, step=1)
top_p_slider = pn.widgets.FloatSlider(name='top-p', start=0.0, end=1.0, value=0.1, step=0.01)
temperature_slider = pn.widgets.FloatSlider(name='Temperature', start=0.0, end=2.0, value=0.0, step=0.1)

# Function to download chat history as a formatted text file
def download_chat_history():
    # Initialize a buffer to store the formatted text
    output = StringIO()
    # Iterate through each message in the chat history
    for message in chat_history:
        if message['role'] == 'user':
            output.write(f"\n\nUser: {message['content']}\n")
        else:
            output.write(f"Charlie: {message['content'].strip()}\n")
    output.seek(0)  # Rewind the buffer to the beginning
    return output

# File download widget for chat history
file_download = pn.widgets.FileDownload(
    callback=download_chat_history,
    filename="Chat.txt",
    label="Download Chat"
)

# Advanced Settings panel content
settings_content = pn.Column(
    pn.pane.Markdown("### Adjust the model parameters as needed to shape the response quality."),
    pn.layout.Spacer(height=10),
    # system_prompt,
    # pn.pane.Markdown("Assign a role to the LLM with the system prompt."),
    # pn.layout.Spacer(height=10),
    top_k_slider,
    pn.pane.Markdown("Top-k controls the diversity of responses. A higher value allows more diverse responses."),
    pn.layout.Spacer(height=10),
    top_p_slider,
    pn.pane.Markdown("Top-p works with Top K to control the randomness of responses. A higher value results in more varied responses."),
    pn.layout.Spacer(height=10),
    temperature_slider,
    pn.pane.Markdown("Temperature controls the randomness in response generation. Higher values make responses more creative."),
)

# Privacy tab content
privacy_content = pn.pane.Markdown("""
Charlie does not log or track any kind of user activity. 

You can download your private chat session logs on the top right.
""")

# Tabs for chat, settings, and privacy
tabs = pn.Tabs(
    ("Chat", chat_interface),
    ("Advanced Settings", settings_content),
    ("Privacy Policy", privacy_content)
)

# Header setup with download button
header = pn.Row(pn.layout.HSpacer(), file_download, styles=dict(background='WhiteSmoke'), align='center')

# Setup the main template
template = pn.template.BootstrapTemplate(
    title='Charlie',
    favicon="Charlie_Logo.png",
    header=header,
    header_background="#000000",
    main=[tabs]
)
template.servable()
