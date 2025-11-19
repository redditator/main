import tempfile
from TTS.api import TTS
import numpy as np
import wave
import librosa, shutil
import sys
from utils.log import log
import time
import subprocess, string
import os

SAMPLE_RATE = 24000

tts_model = TTS("tts_models/en/vctk/vits", gpu=False, progress_bar=False)
tts_speaker = "p243"

class AudioGenerator:
    def __init__(self, pause_duration=0.25):
        self.pause_duration = float(pause_duration)

    def speak(self, text: str):
        groups = self._split_into_groups(text)
        print(f"[debug] generating TTS for {len(groups)} phrase groups")
        temp_files = []
        timestamps = []
        current_time = 0
        start_time = time.time()
        group_size = 3
        for i, group in enumerate(groups):
            progress = (i + 1) / len(groups)
            eta = self._calculate_eta(start_time, progress, len(groups))
            self._print_progress(i, len(groups), f"'{group}'", eta)
            group_audio_file = self._generate_and_trim_group_audio(group)
            temp_files.append(group_audio_file)
            duration = self._get_audio_duration(group_audio_file)

            if any(group.strip().endswith(p) for p in ".!?"):
                silence_path = self._generate_silence(self.pause_duration)
                temp_files.append(silence_path)
                duration += self.pause_duration

            words = group.split()
            if words:
                num_blocks = (len(words) + group_size - 1) // group_size
                block_duration = duration / num_blocks
                for b in range(num_blocks):
                    start_idx = b * group_size
                    end_idx = min((b + 1) * group_size, len(words))
                    block_text = " ".join(words[start_idx:end_idx])
                    timestamps.append({
                        "text": block_text,
                        "start": current_time + b * block_duration,
                        "end": current_time + (b + 1) * block_duration
                    })

            current_time += duration

        self._print_progress(len(groups), len(groups), "Complete!", "0s")
        log()

        final_audio_file = self._concat_audio_files(temp_files)

        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return final_audio_file, timestamps

    def _split_into_groups(self, text: str):
        groups = []
        current_group = []
        for word in text.split():
            current_group.append(word)
            if any(word.endswith(p) for p in string.punctuation):
                groups.append(' '.join(current_group))
                current_group = []
        if current_group:
            groups.append(' '.join(current_group))
        return groups


    def _generate_and_trim_group_audio(self, group: str):
        temp_wav = tempfile.NamedTemporaryFile(delete=False, dir="/tmp", suffix=".wav")

        stdout_backup = sys.stdout
        stderr_backup = sys.stderr
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

        try:
            tts_model.tts_to_file(text=group, speaker=tts_speaker, file_path=temp_wav.name)
        finally:
            sys.stdout.close()
            sys.stderr.close()
            sys.stdout = stdout_backup
            sys.stderr = stderr_backup

        audio_data, sr = librosa.load(temp_wav.name, sr=SAMPLE_RATE)
        start_idx = self._find_audio_start(audio_data, sr)
        end_idx = self._find_audio_end(audio_data, sr)
        trimmed_audio = audio_data[start_idx:end_idx]
        audio_int16 = (trimmed_audio * 32767).astype(np.int16)
        with wave.open(temp_wav.name, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_int16.tobytes())
        return temp_wav.name


    def _generate_silence(self, duration: float):
        samples = int(SAMPLE_RATE * duration)
        silence = np.zeros(samples, dtype=np.int16)
        temp_wav = tempfile.NamedTemporaryFile(delete=False, dir="/tmp", suffix=".wav")
        with wave.open(temp_wav.name, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(silence.tobytes())
        return temp_wav.name

    def _find_audio_start(self, audio_data: np.ndarray, sr: int):
        frame_length = int(0.01 * sr)
        hop_length = frame_length // 2
        energy = []
        for i in range(0, len(audio_data) - frame_length, hop_length):
            frame = audio_data[i:i + frame_length]
            energy.append(np.sqrt(np.mean(frame**2)))
        energy = np.array(energy)
        threshold = np.max(energy) * 0.1
        for i, e in enumerate(energy):
            if e > threshold:
                return max(0, i * hop_length - int(0.02 * sr))
        return 0

    def _find_audio_end(self, audio_data: np.ndarray, sr: int):
        frame_length = int(0.01 * sr)
        hop_length = frame_length // 2
        energy = []
        for i in range(0, len(audio_data) - frame_length, hop_length):
            frame = audio_data[i:i + frame_length]
            energy.append(np.sqrt(np.mean(frame**2)))
        energy = np.array(energy)
        threshold = np.max(energy) * 0.1
        for i in range(len(energy) - 1, -1, -1):
            if energy[i] > threshold:
                return min(len(audio_data), (i + 1) * hop_length + int(0.02 * sr))
        return len(audio_data)

    def _get_audio_duration(self, audio_file: str):
        result = subprocess.run([
            "ffprobe","-v","error","-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1",audio_file
        ], capture_output=True, text=True)
        return float(result.stdout.strip())

    def _concat_audio_files(self, audio_files):
        concat_list = tempfile.NamedTemporaryFile(delete=False, dir="/tmp", suffix=".txt", mode='w')
        for audio_file in audio_files:
            concat_list.write(f"file '{os.path.abspath(audio_file)}'\n")
        concat_list.close()
        output_file = tempfile.NamedTemporaryFile(delete=False, dir="/tmp", suffix=".wav")
        output_file.close()
        subprocess.run([
            "ffmpeg","-y","-f","concat","-safe","0",
            "-i",concat_list.name,"-c","copy",output_file.name
        ], capture_output=True)
        os.remove(concat_list.name)
        return output_file.name

    def _print_progress(self, current, total, status="", eta=""):
        try:
            terminal_width = shutil.get_terminal_size().columns
        except:
            terminal_width = 80
        min_bar_length = 20
        max_bar_length = terminal_width - 60
        bar_length = max(min_bar_length, min(max_bar_length, 40))
        progress = float(current) / float(total) if total > 0 else 0
        block = int(round(bar_length * progress))
        percent = round(progress * 100, 1)
        color_start = "\033[92m"
        color_end = "\033[0m"
        bar = f"{color_start}{'█' * block}{color_end}{'░' * (bar_length - block)}"
        status_text = f"{percent}% ({current}/{total}) {status}"
        if eta:
            status_text += f" | {eta}"
        text = f"\r[{bar}] {status_text}"
        if len(text) > terminal_width:
            available_space = terminal_width - len("[...] ... | ...") - 10
            if available_space > 10:
                truncated_status = status[:available_space] + "..." if len(status) > available_space else status
                status_text = f"{percent}% ({current}/{total}) {truncated_status}"
                if eta:
                    status_text += f" | {eta}"
                text = f"\r[{bar}] {status_text}"
            text = text[:terminal_width-1]
        sys.stdout.write(text)
        sys.stdout.flush()

    def _calculate_eta(self, start_time, progress, total_words):
        if progress == 0:
            return "calculating..."
        elapsed = time.time() - start_time
        if progress > 0:
            total_estimated = elapsed / progress
            remaining = total_estimated - elapsed
            if remaining < 60:
                string = f"{int(remaining)}s"
            else:
                string = f"{int(remaining/60)}m {int(remaining%60)}s"
            return f"{string}{' '*(shutil.get_terminal_size().columns - len(string))}"
        return "calculating..."
