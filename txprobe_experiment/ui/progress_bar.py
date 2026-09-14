import time
from tqdm import tqdm

def wait_seconds_with_progressbar(total_seconds: float, description: str):
    step = total_seconds / 100.0
    if len(description) == 0:
        description = f"Waiting for {total_seconds} seconds."
    with tqdm(total=total_seconds, desc=description) as pbar:
        elapse = 0.0
        while elapse < total_seconds:
            time.sleep(step)
            pbar.update(step)
            elapse += step