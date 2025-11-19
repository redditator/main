from ollama import Client
from utils.log import log

_test = False

class StoryGenerator:
    def __init__(self, model="gemma3:4b"):
        self.model = model
        self.client = Client(host='http://localhost:11434')
        self._ensure_model()

    def _ensure_model(self):
        if not _test:
            try:
                log(f"checking if model '{self.model}' is ready...")
                self.client.generate(
                    model=self.model, 
                    prompt="test",
                    options={'num_predict': 5}
                )
                log(f"model '{self.model}' is ready!")
            except Exception as e:
                log(f"model '{self.model}' not ready: {e}")
                log("pulling model...")
                current_digest = ""
                for progress in self.client.pull(self.model, stream=True):
                    digest = progress.get('digest', '')
                    if digest != current_digest:
                        if 'total' in progress and 'completed' in progress:
                            percent = (progress['completed'] / progress['total']) * 100
                            print(f"\rDownloading: {percent:.1f}%", end='', flush=True)
                        current_digest = digest
                log("\ndownload complete!")
                self._ensure_model()

    def generate(self, prompt: str = None) -> str:
        if _test:
            return "Generate a dramatic, intense, modern Reddit-style story centered on toxic family dynamics or broken relationships. The story MUST START with a Reddit-style question addressed to readers, such as: 'Redditors, am I wrong for what I did?'. The tone should be heavy, emotional, and high-stakes, with shocking reveals, extreme situations, and lasting consequences. Themes may include faking one's own funeral to discover who truly cared, or a partner whose social media fame leads them to humiliate the protagonist publicly until they face harsh consequences. The story should be long, immersive, and include a powerful twist. Provide only the story, no title, no extra commentary, no extra markdown (such as *, __ etc.)."
        else:
            log("generating function called")
            log(f"prompt: {prompt}")
            
            full_response = ""
            try:
                log("sending request to Ollama with streaming...")
                
                stream_response = self.client.generate(
                    model=self.model, 
                    prompt=prompt,
                    stream=True
                )
                
                log("starting to stream response...")
                
                for chunk in stream_response:
                    
                    if 'response' in chunk:
                        text = chunk['response']
                        full_response += text
                    
                    if 'done' in chunk and chunk['done']:
                        log("stream completed!")
                        break
                
                log(f"full story: {len(full_response)} characters")
                return full_response.strip()
                
            except Exception as e:
                log(f"error in generate: {e}")
                return f"error: {e}"