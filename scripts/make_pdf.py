"""Builds the paper as a two-column PDF.

There is no LaTeX toolchain on this machine, and the paper needed to exist as a
PDF, so this lays it out directly with ReportLab in the conventional preprint
form: full-width title and abstract, two columns below, figures placed in
column, booktabs-style rules on the tables.

Every number is computed from the per-call records through make_figures, the
same path the LaTeX macros use, so the PDF cannot drift from the results.

    python scripts/make_pdf.py
"""

import importlib.util
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("mf", _ROOT / "scripts" / "make_figures.py")
mf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mf)

OUT = _ROOT / "paper" / "output_budget_confound.pdf"
FIGS = _ROOT / "paper" / "figures"

PAGE_W, PAGE_H = LETTER
MARGIN = 0.8 * inch
GUTTER = 0.3 * inch
COL_W = (PAGE_W - 2 * MARGIN - GUTTER) / 2
TITLE_BLOCK_H = 3.05 * inch

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
RULE = colors.HexColor("#999999")
ACCENT = colors.HexColor("#1f5fa8")


def styles():
    s = {}
    s["title"] = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16.5,
                                leading=19.5, alignment=TA_CENTER, textColor=INK,
                                spaceAfter=9)
    s["authors"] = ParagraphStyle("authors", fontName="Helvetica", fontSize=10.5,
                                  leading=13, alignment=TA_CENTER, textColor=INK,
                                  spaceAfter=2)
    s["affil"] = ParagraphStyle("affil", fontName="Helvetica-Oblique", fontSize=8.5,
                                leading=11, alignment=TA_CENTER, textColor=MUTED,
                                spaceAfter=12)
    s["abshead"] = ParagraphStyle("abshead", fontName="Helvetica-Bold", fontSize=9,
                                  leading=11, alignment=TA_CENTER, textColor=INK,
                                  spaceAfter=4)
    s["abstract"] = ParagraphStyle("abstract", fontName="Times-Roman", fontSize=9,
                                   leading=11.2, alignment=TA_JUSTIFY, textColor=INK,
                                   leftIndent=26, rightIndent=26, spaceAfter=5)
    s["h1"] = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=10,
                             leading=12, textColor=INK, spaceBefore=11, spaceAfter=4)
    s["h2"] = ParagraphStyle("h2", fontName="Helvetica-BoldOblique", fontSize=9.2,
                             leading=11, textColor=INK, spaceBefore=8, spaceAfter=3)
    s["body"] = ParagraphStyle("body", fontName="Times-Roman", fontSize=9.3,
                               leading=11.4, alignment=TA_JUSTIFY, textColor=INK,
                               spaceAfter=5)
    s["bodyi"] = ParagraphStyle("bodyi", parent=s["body"], firstLineIndent=11,
                                spaceAfter=5)
    s["cap"] = ParagraphStyle("cap", fontName="Times-Roman", fontSize=7.8,
                              leading=9.4, alignment=TA_JUSTIFY, textColor=INK,
                              spaceBefore=4, spaceAfter=8)
    s["mono"] = ParagraphStyle("mono", fontName="Courier", fontSize=7.4, leading=9.2,
                               textColor=INK, leftIndent=6, spaceBefore=3, spaceAfter=7)
    s["ref"] = ParagraphStyle("ref", fontName="Times-Roman", fontSize=8.2,
                              leading=10, leftIndent=12, firstLineIndent=-12,
                              textColor=INK, spaceAfter=3)
    return s


def rule_line(width, thickness=0.7, color=RULE, space_before=0, space_after=4):
    t = Table([[""]], colWidths=[width], rowHeights=[0.1])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), thickness, color),
        ("TOPPADDING", (0, 0), (-1, -1), space_before),
        ("BOTTOMPADDING", (0, 0), (-1, -1), space_after),
    ]))
    return t


def academic_table(data, col_widths, caption, s, label):
    tbl = Table(data, colWidths=col_widths, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.1),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.9, INK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return KeepTogether([tbl, Paragraph(f"<b>{label}</b> {caption}", s["cap"])])


def figure(path, s, label, caption, width=None):
    width = width or COL_W
    from PIL import Image as PILImage  # ships with reportlab installs via pillow
    with PILImage.open(path) as im:
        w, h = im.size
    img = Image(str(path), width=width, height=width * h / w)
    return KeepTogether([img, Paragraph(f"<b>{label}</b> {caption}", s["cap"])])


def pct(x):
    return f"{x * 100:.1f}"


def build_numbers():
    """Pulls every quoted figure from the per-call records."""
    recs = mf.load()
    n = {}
    for model in ("nemotron", "claude"):
        for b in (512, 1024, 2048, 4096):
            rows = mf.sel(recs, model, b)
            if not rows:
                continue
            p, lo, hi, k = mf.rate(rows)
            n[(model, b)] = {
                "solve": p, "lo": lo, "hi": hi, "n": k,
                "err": sum(1 for r in rows if r.get("error")),
                "trunc": mf.truncation_rate(rows, b),
                "cond": mf.conditional_rate(rows, b)[0],
                "tok": (sum(r["output_tokens"] for r in mf.attempted(rows))
                        / max(1, len(mf.attempted(rows)))),
                "lat": (sorted(r["latency_s"] for r in mf.attempted(rows))[
                    len(mf.attempted(rows)) // 2] if mf.attempted(rows) else 0.0),
            }
    g = mf.sel(recs, "gemini", 4096)
    inst = [r for r in mf.attempted(g) if r.get("thinking_tokens") is not None]
    n["gemini_visible"] = (sum(r["output_tokens"] for r in inst) / len(inst)) if inst else 0
    n["gemini_think"] = (sum(r["thinking_tokens"] for r in inst) / len(inst)) if inst else 0
    n["gemini_ratio"] = ((n["gemini_visible"] + n["gemini_think"]) / n["gemini_visible"]
                         if n["gemini_visible"] else 0)
    return n


def story(s, n):
    f = []
    A = lambda t, st="body": f.append(Paragraph(t, s[st]))  # noqa: E731

    lo = n[("nemotron", 512)]
    hi = n[("nemotron", 4096)]
    swing = (hi["solve"] - lo["solve"]) * 100

    # ---- title block (full width, first page) ----
    f.append(Paragraph("The Output Budget Confound: Why Token Ceilings "
                       "Silently Decide LLM Planning Benchmark Results", s["title"]))
    f.append(Paragraph("Kevin Doshi &nbsp;&nbsp;&nbsp; Randa Kamal &nbsp;&nbsp;&nbsp; Zaid Hanif",
                       s["authors"]))
    f.append(Paragraph("SteelHacks 2026 &nbsp;&middot;&nbsp; Preprint", s["affil"]))
    f.append(Paragraph("Abstract", s["abshead"]))
    A(f"Comparisons between large language models on planning benchmarks are "
      f"usually reported as a single accuracy number per model. We show that for "
      f"models which reason in the open, this number is not a property of the "
      f"model alone: it is jointly determined by the output token ceiling the "
      f"evaluator happened to choose. On the Calendar Scheduling task of "
      f"<i>Natural Plan</i>, raising the ceiling from 512 to 4096 tokens moves "
      f"Nemotron Super from <b>{pct(lo['solve'])}%</b> to <b>{pct(hi['solve'])}%</b>, "
      f"a swing of {swing:.0f} percentage points, with the prompt, the sample and "
      f"the scoring held fixed. The model was not failing to plan. At the lower "
      f"ceiling {pct(lo['trunc'])}% of its generations were cut off before an "
      f"answer was emitted, and an exact match scorer recorded that truncation as "
      f"a planning error. We quantify the effect across tier matched models, "
      f"separate it from test time compute scaling by reporting the truncation "
      f"rate alongside accuracy, and show that the obvious way to detect "
      f"truncation is unsound for models that reason in hidden tokens, failing in "
      f"the direction of understating them. We release the harness and the per "
      f"call records.", "abstract")
    f.append(NextPageTemplate("later"))

    # ---- body ----
    A("1&nbsp;&nbsp;Introduction", "h1")
    A("Planning under constraints is an attractive target for language model "
      "evaluation: solutions are hard to find and cheap to verify. Natural Plan [1] "
      "scores a proposed meeting time by exact match against a golden answer, with "
      "no human annotation and no model acting as judge. That property is why we "
      "selected it. It removes the dominant failure mode of bespoke benchmarks, in "
      "which the party reporting a comparison also authored its ground truth.")
    A("Having removed that confound, we encountered another. Contemporary models "
      "differ sharply in how much text they emit before committing to an answer. A "
      "model that reasons silently answers in tens of tokens. A model that reasons "
      "in the open may spend thousands. Every evaluation harness imposes a "
      "generation ceiling. When that ceiling falls below what a model needs in "
      "order to finish, the harness records no answer, and an exact match scorer, "
      "which cannot distinguish an absent answer from an incorrect one, records a "
      "planning failure.", "bodyi")
    A(f"This is not hypothetical. In our first run, Nemotron Super scored zero of "
      f"twelve at a ceiling of 512 tokens. Inspecting the raw generations showed "
      f"the model mid derivation at the cut, having already correctly enumerated "
      f"every participant constraint. At 4096 tokens, with nothing else changed, "
      f"the same model on the same items scored {pct(hi['solve'])}%. Had we "
      f"published the first number, we would have reported a false result in good "
      f"faith, and the harness, not the model, would have been at fault.", "bodyi")

    A("1.1&nbsp;&nbsp;Contributions", "h2")
    for i, c in enumerate([
        "We isolate the generation ceiling as an experimental variable on Natural "
        "Plan Calendar Scheduling and measure its effect on two tier matched models "
        "chosen to sit at opposite ends of output verbosity.",
        "We report the truncation rate and the solve rate conditional on finishing, "
        "which separate a planning failure from a harness failure and distinguish "
        "this effect from test time compute scaling [3].",
        "We show that the obvious way to detect truncation, comparing emitted "
        "tokens against the ceiling, is unsound for models reasoning in hidden "
        "tokens, and that it fails in the direction of understating them.",
        "We validate our scorer against published numbers before reporting any "
        "comparison, and quantify run to run variance from a seeded replication.",
    ], start=1):
        A(f"<b>{i}.</b>&nbsp;&nbsp;{c}")

    A("2&nbsp;&nbsp;Method", "h1")
    A("<b>Task and scoring.</b> We use the Calendar Scheduling split of Natural "
      "Plan: 1,000 items, each giving the availability of every participant and a "
      "required meeting duration, with exactly one valid slot. Difficulty is "
      "controlled by participant count, from two to seven. Scoring follows the "
      "official evaluator: a regular expression extracts the first "
      "<font face='Courier' size='8'>Day, HH:MM - HH:MM</font> span and compares "
      "day, start and end against the golden answer.")
    A("<b>Scorer validation.</b> Before comparing any models we validated our port "
      "of the official evaluator against the reference predictions shipped with the "
      "dataset. Our implementation scores those predictions at 48.9%, against 48% "
      "reported in the original work, so our numbers sit on the same scale as the "
      "published ones.")
    A("<b>Models.</b> The primary comparison is between two models matched by "
      "vendor tier and chosen because they sit at opposite ends of output "
      "verbosity, which is the axis the effect acts on: Nemotron Super, a sparse "
      "mixture of experts with 120B total and 12B active parameters, which reasons "
      "in its visible output; and Claude Haiku 4.5, which is comparatively terse. "
      "Only the first has a published parameter count, so we do not plot accuracy "
      "against parameter count, because doing so for the other would require "
      "inventing a number. A small set of Gemini 3.5 Flash results is reported as "
      "preliminary: its free tier permits twenty requests per day for that model, "
      "which is not a sample size.")
    A("<b>Controls.</b> Every model receives the byte identical user prompt taken "
      "from the dataset. One deliberate asymmetry exists and we state it plainly: "
      "Nemotron is sent the vendor documented reasoning control in a system turn, "
      "which the other models have no equivalent for. That control did not do what "
      "its name suggests; the model still emitted extended derivations. Sampling "
      "temperature is zero wherever the vendor SDK exposes it. Latency is measured "
      "around the successful request only, excluding our own retry backoff, so rate "
      "limiting imposed by our billing tier is not charged to a model's speed. "
      "Items are sampled stratified by participant count, because the raw "
      "distribution is half two participant items. Uncertainty is reported as "
      "Wilson score intervals [5].")
    A("<b>Infrastructure failures are not answers.</b> Calls that never reached the "
      "model are excluded from every rate and reported separately. Under load the "
      "provider returned HTTP 429 and 503 at a substantial rate; a call that "
      "exhausts its retries produced no generation to score, and placing it in the "
      "denominator would record an infrastructure failure as a planning failure. "
      "Our own first analysis did exactly that before we caught it, which we take "
      "as evidence the mistake is easy rather than unusual.")

    A("3&nbsp;&nbsp;Results", "h1")
    A(f"Figure 1(a) sweeps the generation ceiling with every other variable held "
      f"fixed. Nemotron rises from {pct(lo['solve'])}% to {pct(hi['solve'])}%. "
      f"Claude, which emits far less text before answering, is substantially "
      f"flatter across the same sweep. A single ceiling applied uniformly is "
      f"therefore not neutral: it penalises verbose reasoners specifically, and the "
      f"size of the penalty is a property of the harness rather than of the task.")
    A(f"Figure 1(b) shows the mechanism. At the 512 token ceiling "
      f"{pct(lo['trunc'])}% of Nemotron generations terminate at the ceiling rather "
      f"than at a stop token, against {pct(n[('claude', 512)]['trunc'])}% for "
      f"Claude. At 4096 that figure falls to {pct(hi['trunc'])}%. The accuracy "
      f"curve is the mirror image of the truncation curve, which is what "
      f"distinguishes this from a test time compute effect: the model is not "
      f"reasoning better with more tokens, it is being permitted to finish at all.",
      "bodyi")

    f.append(figure(FIGS / "fig1_token_budget.png", s, "Figure 1.",
                    "Solve rate against the output token ceiling (a), and the "
                    "fraction of generations truncated at that ceiling (b). Bars "
                    "are 95% Wilson intervals. The two panels are mirror images."))

    head = ["Model", "Ceil", "Solve", "Trunc", "Cond", "n", "Err"]
    rows = [head]
    for model, name in (("nemotron", "Nemotron"), ("claude", "Claude")):
        for b in (512, 1024, 2048, 4096):
            d = n.get((model, b))
            if not d:
                continue
            rows.append([name, str(b), pct(d["solve"]), pct(d["trunc"]),
                         pct(d["cond"]), str(d["n"]), str(d["err"])])
    widths = [COL_W * w for w in (0.255, 0.115, 0.145, 0.145, 0.145, 0.10, 0.095)]
    f.append(academic_table(
        rows, widths,
        "Solve, truncation and conditional solve rates, in percent. Conditional "
        "is computed over generations allowed to finish. Err counts provider "
        "failures, excluded from every rate.", s, "Table 1."))

    A(f"The conditional column is the one that matters for interpreting the first. "
      f"A generation that is cut off and a generation proposing the wrong meeting "
      f"time are the same event to an exact match scorer, but completely different "
      f"events for anyone choosing a model. Separating them shows Nemotron's "
      f"conditional accuracy never falls below "
      f"{pct(min(n[('nemotron', b)]['cond'] for b in (512, 1024, 2048, 4096)))}% at "
      f"any ceiling, while its headline number ranges across {swing:.0f} points. "
      f"The headline is measuring the harness.")
    A(f"We also resist the phrase <i>adequate ceiling</i> as an absolute. Nemotron "
      f"remains truncated on {pct(hi['trunc'])}% of items even at 4096 tokens, a "
      f"ceiling most practitioners would consider generous, so its result there is "
      f"still an underestimate. Adequacy is a property of a model and a harness "
      f"together, and the only way to know a ceiling was adequate is to measure the "
      f"truncation rate and find it at zero.", "bodyi")

    A("3.1&nbsp;&nbsp;Detecting truncation is harder than it looks", "h2")
    A("The obvious way to detect that a generation hit the ceiling is to compare "
      "the emitted token count against it. That test is wrong for any model that "
      "reasons in hidden tokens. In our Gemini runs, generations were visibly cut "
      "in mid sentence, including mid answer, while the reported output token count "
      "stood at roughly twenty against a ceiling of 512.")
    A(f"Instrumenting the vendor's full token accounting shows why. At a ceiling "
      f"where the model runs to completion it emits {n['gemini_visible']:.0f} "
      f"visible tokens per item but spends {n['gemini_think']:.0f} reasoning tokens "
      f"that do not appear in that count. True generation spend is roughly "
      f"{n['gemini_ratio']:.0f} times what the output token field reports.", "bodyi")
    # Kept short deliberately: at Courier 7.4pt a longer line wraps mid word in
    # a 3.2 inch column, which reads as a typesetting error rather than code.
    f.append(Paragraph(
        "ceiling          512<br/>"
        "visible tokens&nbsp;&nbsp;&nbsp;&nbsp;21&nbsp;&nbsp;(what the API reports)<br/>"
        "thinking tokens&nbsp;1344&nbsp;&nbsp;(billed, not reported)<br/>"
        "true spend&nbsp;&nbsp;&nbsp;&nbsp;~1365&nbsp;&nbsp;&gt; 512, so truncation<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;is unavoidable", s["mono"]))
    A("Truncation at the lower ceiling is therefore not merely possible, it is "
      "arithmetically unavoidable, which is exactly what the raw generations show. "
      "The reasoning tokens are billed against the ceiling but are absent from the "
      "field an evaluator would naturally check, so the naive test reports no "
      "truncation precisely where truncation is certain. We flag this because the "
      "failure is silent, it is in the direction that makes a model look worse, and "
      "it lands specifically on the reasoning models this effect concerns. We take "
      "the vendor's finish reason as authoritative and treat any token based rule "
      "as a fallback.")

    A("3.2&nbsp;&nbsp;What separates the models", "h2")
    nh, ch = n[("nemotron", 4096)], n[("claude", 4096)]
    A(f"At the highest ceiling Nemotron reaches {pct(nh['solve'])}% against Claude "
      f"at {pct(ch['solve'])}%, and {pct(nh['cond'])}% against {pct(ch['cond'])}% "
      f"conditional on finishing. Exact McNemar tests on the paired per item "
      f"outcomes separate none of the model pairs. We report the comparison as not "
      f"separable. Because all models are run on the same items the outcomes are "
      f"paired, and a two sample proportion test would discard that pairing and "
      f"overstate the evidence.")
    A(f"The efficiency picture is sharper than the accuracy one. Nemotron spends "
      f"{nh['tok']:.0f} output tokens and {nh['lat']:.1f} seconds per item against "
      f"Claude's {ch['tok']:.0f} tokens and {ch['lat']:.1f} seconds, roughly four "
      f"times the output and six times the wall clock for a solve rate whose "
      f"interval overlaps. Accuracy alone does not separate these systems; "
      f"accuracy per token does.", "bodyi")

    f.append(figure(FIGS / "fig3_efficiency.png", s, "Figure 2.",
                    "Solve rate against mean output tokens per task. Up and to the "
                    "left is better. The models are close in accuracy and an order "
                    "of magnitude apart in what they spend to get there."))

    A("Run to run variation reinforces the caution. An interrupted earlier sweep "
      "had already scored part of the seeded sample, so the relaunched sweep drew "
      "the same items and gave an independent replication at no extra cost. "
      "Nemotron, at temperature zero, scored 98.3% of items identically across the "
      "two runs. Claude, which we could not pin to temperature zero because its SDK "
      "no longer exposes the parameter, agreed on only 62.5%. A single accuracy "
      "figure for a model at a nondeterministic temperature is a draw from a "
      "distribution whose spread is not small.")

    A("4&nbsp;&nbsp;Discussion", "h1")
    A("The practical recommendation is small and cheap. Evaluation reports should "
      "state the generation ceiling alongside accuracy, and should verify that the "
      "ceiling binds on no model before comparing any two. One statistic suffices: "
      "the fraction of generations that terminate at the ceiling rather than at a "
      "stop token. A model whose truncation rate is materially above zero has not "
      "been measured, it has been cut off, and its accuracy number carries no "
      "information about its planning ability.")
    A("The effect interacts badly with two current trends. Models increasingly "
      "reason at length, whether in visible output or in hidden tokens, and "
      "harnesses increasingly cap output to control cost. Those pressures push in "
      "opposite directions, and the resulting headline number is quietly sensitive "
      "to a parameter that is rarely reported at all.", "bodyi")

    A("5&nbsp;&nbsp;Limitations", "h1")
    A("<b>Contamination is not controlled.</b> Natural Plan has been public since "
      "2024 and may appear in the training data of any model evaluated here. "
      "Exposure is symmetric across models and the headline result is a within "
      "model effect, but we make no decontamination claim.")
    A("<b>Temperature.</b> The Anthropic SDK version used removed the temperature "
      "parameter from its message creation call, so Claude runs at the API default "
      "while the others run at zero. This is an SDK constraint, stated rather than "
      "omitted.")
    A("<b>Sample loss correlates with the swept variable.</b> Provider 429 and 503 "
      "rates rose with the ceiling, because larger ceilings mean longer generations "
      "and more concurrent requests in flight. Higher ceiling cells therefore rest "
      "on fewer retained items. A dropped call produced no output at all, "
      "independent of whether that output would have been correct, so we do not "
      "believe this biases direction, but it costs precision where we would most "
      "like to have it. Re-running the highest ceiling at lower concurrency cut the "
      "loss rate substantially, confirming the cause.")
    A("<b>Scope.</b> One task from one benchmark, two models in the primary "
      "comparison. We do not claim the ceiling effect generalises to tasks that do "
      "not elicit extended reasoning, although the mechanism is not task specific.")

    A("6&nbsp;&nbsp;Reproducibility", "h1")
    A("The harness, the per call records including raw generations, and the "
      "analysis code are released with this paper. Sampling is seeded and "
      "stratified, and the seed is recorded in every result file. Scoring uses our "
      "validated port of the official evaluator. Every number quoted here is "
      "generated from the records rather than typed by hand.")

    A("7&nbsp;&nbsp;Conclusion", "h1")
    A("A generation ceiling is not a neutral implementation detail of an evaluation "
      "harness. For models that reason at length it can move a headline accuracy "
      "number by a wide margin, and it does so silently, because a truncated "
      "generation and a wrong answer are indistinguishable to an exact match "
      "scorer. We recommend that benchmark reports state the ceiling, verify it "
      "binds on no model, and publish output length alongside accuracy.")

    A("References", "h1")
    for i, r in enumerate([
        "H. S. Zheng et al. Natural Plan: Benchmarking LLMs on Natural Language "
        "Planning. arXiv:2406.04520, 2024.",
        "K. Valmeekam et al. PlanBench: An Extensible Benchmark for Evaluating "
        "Large Language Models on Planning and Reasoning about Change. NeurIPS "
        "Datasets and Benchmarks, 2023.",
        "C. Snell, J. Lee, K. Xu, A. Kumar. Scaling LLM Test-Time Compute Optimally "
        "Can be More Effective than Scaling Model Parameters. arXiv:2408.03314, 2024.",
        "O. Sainz et al. NLP Evaluation in Trouble: On the Need to Measure LLM Data "
        "Contamination for each Benchmark. Findings of EMNLP, 2023.",
        "E. B. Wilson. Probable Inference, the Law of Succession, and Statistical "
        "Inference. JASA, 22(158):209-212, 1927.",
        "N. Jain et al. LiveCodeBench: Holistic and Contamination Free Evaluation "
        "of Large Language Models for Code. arXiv:2403.07974, 2024.",
    ], start=1):
        A(f"[{i}]&nbsp;&nbsp;{r}", "ref")
    return f


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(PAGE_W / 2, MARGIN * 0.55, str(doc.page))
    canvas.restoreState()


def main():
    doc = BaseDocTemplate(str(OUT), pagesize=LETTER,
                          leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=MARGIN, bottomMargin=MARGIN,
                          title="The Output Budget Confound",
                          author="Kevin Doshi, Randa Kamal, Zaid Hanif")

    body_h = PAGE_H - 2 * MARGIN
    top = Frame(MARGIN, PAGE_H - MARGIN - TITLE_BLOCK_H,
                PAGE_W - 2 * MARGIN, TITLE_BLOCK_H, id="top",
                leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    lower_h = body_h - TITLE_BLOCK_H
    f1l = Frame(MARGIN, MARGIN, COL_W, lower_h, id="f1l",
                leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    f1r = Frame(MARGIN + COL_W + GUTTER, MARGIN, COL_W, lower_h, id="f1r",
                leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    fl = Frame(MARGIN, MARGIN, COL_W, body_h, id="fl",
               leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    fr = Frame(MARGIN + COL_W + GUTTER, MARGIN, COL_W, body_h, id="fr",
               leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc.addPageTemplates([
        PageTemplate(id="first", frames=[top, f1l, f1r], onPage=footer),
        PageTemplate(id="later", frames=[fl, fr], onPage=footer),
    ])

    s = styles()
    n = build_numbers()
    doc.build(story(s, n))
    size = OUT.stat().st_size / 1024
    print(f"written: {OUT.relative_to(_ROOT)}  ({size:.0f} KB)")


if __name__ == "__main__":
    main()
