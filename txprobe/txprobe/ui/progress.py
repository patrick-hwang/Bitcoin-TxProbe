"""Progress bar utilities."""

from __future__ import annotations

import asyncio

from tqdm import tqdm


async def wait_seconds_with_progressbar(
    seconds: float,
    description: str = "Waiting",
) -> None:
    """Sleep for *seconds* while showing a tqdm progress bar.

    Args:
        seconds: Total seconds to wait.
        description: Label for the progress bar.
    """
    total = int(seconds)
    if total <= 0:
        return
    with tqdm(total=total, desc=description, unit="s", ncols=80) as pbar:
        for _ in range(total):
            await asyncio.sleep(1)
            pbar.update(1)
