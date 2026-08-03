import json
import time
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.console import Console, Group
from rich.text import Text


class ProgressUI:
    def __init__(self):
        self.console = Console()
        self._live = None
        self._run_idx = 0
        self._run_total = 0
        self._round_idx = 0
        self._round_total = 0
        self._source_set = []
        self._sink_set = []
        self._phase_status = {1: "", 2: "", 3: ""}
        self._completed_rounds = []
        self._wait_label = ""
        self._wait_current = 0.0
        self._wait_total = 0.0
        self._has_wait = False
        self._setup_detail = ""
        self._groundtruth = None
        self._inference = None
        self._completed_runs = []
        self._run_active = False
        self._adjacency = None

    def start(self):
        self._live = Live(
            self._render(),
            console=self.console,
            screen=False,
            refresh_per_second=4,
            transient=False,
        )
        self._live.__enter__()

    def stop(self):
        if self._live:
            self._live.__exit__(None, None, None)
            self._live = None

    def _render(self):
        elements = [Text("TxProbe Experiment", style="bold cyan")]

        if self._run_total > 0:
            p = Progress(TextColumn("{task.description}"), BarColumn(), TextColumn("{task.completed}/{task.total}"))
            p.add_task(f"Run {self._run_idx}/{self._run_total}", total=self._run_total, completed=self._run_idx)
            elements.append(p)

        elements.extend(self._completed_runs)

        if self._run_active:
            if self._completed_rounds:
                elements.append(Text("Rounds completed:", style="bold"))
                elements.extend(self._completed_rounds)
                elements.append(Text(""))

            if self._round_total > 0:
                src_str = ",".join(str(s) for s in self._source_set)
                snk_str = ",".join(str(s) for s in self._sink_set)
                elements.append(Text(f"Round {self._round_idx}/{self._round_total}  [{src_str}]→[{snk_str}]"))

                table = Table(show_header=False, box=None, padding=(0, 1))
                table.add_column("Phase", style="bold")
                table.add_column("Status")
                table.add_row("1: INV all conflicting txs to all peers", _status_icon(self._phase_status[1]))
                table.add_row("2: flood->sink → parents->source → markers->source", _status_icon(self._phase_status[2]))
                table.add_row("3: INV marker txs to sink set", _status_icon(self._phase_status[3]))
                elements.append(table)

            if self._setup_detail:
                elements.append(Text(self._setup_detail, style="dim"))

            if self._adjacency is not None:
                elements.append(Text(self._adjacency))

            if self._groundtruth is not None:
                elements.append(Text("Groundtruth:", style="bold"))
                for row in self._groundtruth:
                    elements.append(Text("  " + json.dumps(row)))

            if self._inference is not None:
                elements.append(Text("Inference:", style="bold"))
                for row in self._inference:
                    elements.append(Text("  " + json.dumps(row)))

        if self._has_wait:
            p2 = Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                TextColumn("{task.completed:.0f}/{task.total:.0f}s"),
            )
            p2.add_task(self._wait_label, total=self._wait_total, completed=self._wait_current)
            elements.append(p2)

        return Panel(Group(*elements), title="TxProbe", border_style="cyan")

    def _refresh(self):
        if self._live:
            self._live.update(self._render())

    def start_experiment(self, runs):
        self._run_total = runs
        self._run_idx = 0
        self._completed_runs = []
        self._run_active = False
        self._refresh()

    def start_run(self, idx, total):
        self._run_active = True
        self._run_idx = idx
        self._round_idx = 0
        self._round_total = 0
        self._phase_status = {1: "", 2: "", 3: ""}
        self._completed_rounds = []
        self._has_wait = False
        self._setup_detail = ""
        self._groundtruth = None
        self._inference = None
        self._adjacency = None
        self._refresh()

    def start_round(self, idx, total, source_set, sink_set):
        self._round_idx = idx
        self._round_total = total
        self._source_set = source_set
        self._sink_set = sink_set
        self._phase_status = {1: "", 2: "", 3: ""}
        self._has_wait = False
        self._refresh()

    def finalize_round(self):
        src_str = ",".join(str(s) for s in self._source_set)
        snk_str = ",".join(str(s) for s in self._sink_set)
        line = Text(f"  Round {self._round_idx}/{self._round_total}  [{src_str}]→[{snk_str}]  ")
        line.append(Text.from_markup(_status_icon(self._phase_status[1])))
        line.append("  ")
        line.append(Text.from_markup(_status_icon(self._phase_status[2])))
        line.append("  ")
        line.append(Text.from_markup(_status_icon(self._phase_status[3])))
        self._completed_rounds.append(line)
        self._phase_status = {1: "", 2: "", 3: ""}
        self._refresh()

    def update_phase(self, phase_num, status):
        self._phase_status[phase_num] = status
        self._refresh()

    def update_wait(self, label, current, total):
        self._wait_label = label
        self._wait_current = current
        self._wait_total = total
        self._has_wait = True
        self._refresh()

    def hide_wait(self):
        self._has_wait = False
        self._refresh()

    def update_setup(self, detail):
        self._setup_detail = detail
        self._refresh()

    def show_adjacency(self, text):
        self._adjacency = text
        self._refresh()

    def update_matrices(self, groundtruth, inference):
        self._groundtruth = groundtruth
        self._inference = inference
        self._refresh()

    def finalize_run(self, metrics):
        run_el = []
        run_el.append(Text(f"── Run {self._run_idx}/{self._run_total} ──", style="bold cyan"))

        if self._completed_rounds:
            run_el.append(Text("Rounds:", style="bold"))
            run_el.extend(self._completed_rounds)

        if self._adjacency is not None:
            run_el.append(Text(self._adjacency))

        if self._groundtruth is not None:
            run_el.append(Text("Groundtruth:", style="bold"))
            for row in self._groundtruth:
                run_el.append(Text("  " + json.dumps(row)))

        if self._inference is not None:
            run_el.append(Text("Inference:", style="bold"))
            for row in self._inference:
                run_el.append(Text("  " + json.dumps(row)))

        m = metrics
        run_el.append(Text(
            f"  tp={m.tp}  tn={m.tn}  fp={m.fp}  fn={m.fn}  "
            f"precision={m.precision:.4f} recall={m.recall:.4f} accuracy={m.accuracy:.4f}"
        ))

        self._completed_runs.append(Group(*run_el))
        self._run_active = False
        self._completed_rounds = []
        self._round_idx = 0
        self._round_total = 0
        self._phase_status = {1: "", 2: "", 3: ""}
        self._has_wait = False
        self._setup_detail = ""
        self._groundtruth = None
        self._inference = None
        self._adjacency = None
        self._refresh()

    def countdown(self, label, total_seconds, step=0.25):
        elapsed = 0.0
        while elapsed < total_seconds:
            self.update_wait(label, elapsed, total_seconds)
            time.sleep(step)
            elapsed += step
        self.hide_wait()

    def done(self):
        self.stop()


def _status_icon(s):
    if s == "running":
        return "[yellow]▶ running[/]"
    if s == "done":
        return "[green]✓ done[/]"
    if s == "error":
        return "[red]✗ error[/]"
    return "[dim]pending[/]"
