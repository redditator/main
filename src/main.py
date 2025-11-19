from pathlib import Path
import shutil, subprocess
import yaml
import os, gc
from utils.story import StoryGenerator
from utils.audio import AudioGenerator
from utils.video import VideoCreator
from utils.log import log

with open("config.yml") as f:
    cfg = yaml.safe_load(f)

class App:
    def __init__(self, config: dict):
        os.makedirs(config["paths"]["output_video"], exist_ok=True)
        os.makedirs(config["paths"]["video_backgrounds"], exist_ok=True)
        self.config = config
        self.story_gen = StoryGenerator(config["config"]["ollama_model"])
        self.audio_gen = AudioGenerator()
        self.video_gen = VideoCreator(config["paths"]["video_backgrounds"], config)

    def run(self, prompt: str):
        print("[debug] generating story...")
        story = self.story_gen.generate(prompt)
        audio_file, timestamps = self.audio_gen.speak(story)
        video_file = self.video_gen.create_video(audio_file, timestamps)
        del story
        gc.collect()
        log("")
        
        return video_file

if __name__ == "__main__":
    with open("config.yml") as f:
        cfg = yaml.safe_load(f)
    app = App(cfg)
    output = app.run(cfg["story_prompt"])
    log("video saved at:", output)