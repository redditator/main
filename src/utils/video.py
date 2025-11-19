import os, random
import subprocess, string
from pathlib import Path
from utils.log import log
from fontTools.ttLib import TTFont

class VideoCreator:
    def __init__(self, backgrounds_folder: str, config: dict):
        self.backgrounds_folder = backgrounds_folder
        self.config = config
        self.resolution = config["config"]["video_resolution"]
        self.width, self.height = map(int, self.resolution.split('x'))

    def create_video(self, audio_path: str, timestamps=None):
        files = [
            os.path.join(self.backgrounds_folder, f)
            for f in os.listdir(self.backgrounds_folder)
            if f.endswith((".mp4", ".mov"))
        ]
        if not files:
            raise ValueError("no background videos found in folder.")

        audio_duration = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", audio_path
        ]).strip())

        output_dir = os.path.abspath(self.config["paths"]["output_video"])
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "final_video.mp4")

        if timestamps:
            self._create_video_with_subtitles_single_pass(files, audio_path, audio_duration, timestamps, output_path)
        else:
            self._create_video_single_pass(files, audio_path, audio_duration, output_path)

        return output_path

    def _create_video_with_subtitles_single_pass(self, files, audio_path, audio_duration, timestamps, output_path):
        subtitle_file = "/tmp/subtitles.ass"
        self._create_subtitle_ass_file(timestamps, subtitle_file, audio_duration)

        concat_file = "/tmp/concat_list.txt"
        self._create_concat_list(files, audio_duration, concat_file)

        subtitle_file_abs = os.path.abspath(subtitle_file)
        vf_filter = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={self.width}:{self.height},subtitles={subtitle_file_abs}:fontsdir=sources/fonts:force_style='Outline=3'"
        )

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", audio_path,
            "-vf", vf_filter,
            "-r", "60",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-stats",
            output_path
        ]
        if not self.config.get("debug", False):
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        else:
            subprocess.run(ffmpeg_cmd, check=True)

        if os.path.exists(concat_file):
            os.remove(concat_file)
        if os.path.exists(subtitle_file):
            os.remove(subtitle_file)

    def _create_video_single_pass(self, files, audio_path, audio_duration, output_path):
        concat_file = "/tmp/concat_list.txt"
        self._create_concat_list(files, audio_duration, concat_file)

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", audio_path,
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase:flags=lanczos,crop={self.width}:{self.height}",
            "-r", "60",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-stats",
            output_path
        ]
        if not self.config.get("debug", False):
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        else:
            subprocess.run(ffmpeg_cmd, check=True)

        if os.path.exists(concat_file):
            os.remove(concat_file)

    def _create_concat_list(self, files, audio_duration, concat_file):
        with open(concat_file, "w") as f:
            current_time = 0
            i = 0
            while current_time < audio_duration:
                source_file = files[i % len(files)]
                absolute_source_file = os.path.abspath(source_file)
                source_duration = float(subprocess.check_output([
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of",
                    "default=noprint_wrappers=1:nokey=1", source_file
                ]).strip())
                time_needed = min(source_duration, audio_duration - current_time)
                f.write(f"file '{absolute_source_file}'\n")
                f.write(f"inpoint 0\n")
                f.write(f"outpoint {time_needed}\n")
                f.write(f"duration {time_needed}\n")
                current_time += time_needed
                i += 1

    def __fetch_font_name(self):
        font_file = self.config['paths']['subtitle_font']
        ttf_path = str(font_file)

        font = TTFont(ttf_path)
        name_records = font['name'].names

        for record in name_records:
            if record.nameID == 1:
                try:
                    return record.string.decode(record.getEncoding())
                except:
                    return record.string.decode('utf-8', errors='ignore')

        return font.stem


    def _create_subtitle_ass_file(self, timestamps: list, subtitle_file: str, video_duration: float):
        with open(subtitle_file, 'w', encoding='utf-8') as f:
            f.write("[Script Info]\n")
            f.write("ScriptType: v4.00+\n")
            f.write(f"PlayResX: {self.width}\n")
            f.write(f"PlayResY: {self.height}\n")
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            f.write(f"Style: Default,{self.__fetch_font_name()},75,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1\n")
            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            for i, ts in enumerate(timestamps):
                start_str = self._seconds_to_ass_time(ts['start'])
                end_str = self._seconds_to_ass_time(ts['end'])
                text = ts['text'].replace('\n','\\N')
                f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\an5\\q2\\t(0,150,\\fs60,\\fs75)}}{text}\n")

    def _seconds_to_ass_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds - int(seconds)) * 100)
        return f"{hours:d}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
