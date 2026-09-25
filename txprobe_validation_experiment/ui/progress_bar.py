import time
from tqdm import tqdm

def wait_seconds_with_progressbar(
        total_seconds: float, 
        description: str = "",
        update_interval: float = 0.1,
    ) -> None:
    """Wait a specific amount of time.
    :param total_seconds: total time to wait.
    :param description: content to be display.
    :param update_interval: the period to update the progress bar, default = 0.1 second
    """
    if total_seconds <= 0:
        return
    
    if not description:
        description = f"Waiting for {total_seconds} seconds."

    start_time = time.monotonic()
    last_elapsed = 0.0
    
    with tqdm(
        total=total_seconds, 
        desc=description,
        unit="s",
        bar_format="{l_bar}{bar} | {n:.1f}/{total_fmt}s [{elapsed}<{remaining}]",
    ) as pbar:
        while True:
            now = time.monotonic()
            current_elapsed = min(now - start_time, total_seconds)

            delta = current_elapsed - last_elapsed
            if delta > 0:
                pbar.update(delta)
                last_elapsed = current_elapsed

            if current_elapsed >= total_seconds:
                break

            remaining = total_seconds - current_elapsed
            time.sleep(min(update_interval, remaining))