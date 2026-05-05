"""Generate a multi-section scientific test PDF with bold headers."""
import fitz

doc  = fitz.open()
font = fitz.Font("helv")
bold = fitz.Font("hebo")

SECTIONS = [
    ("ABSTRACT", False,
     "Rapid Serial Visual Presentation (RSVP) allows readers to process text "
     "at speeds significantly above their baseline rate by eliminating saccadic "
     "eye movements. This paper reviews the empirical literature on RSVP, "
     "examines the role of the Optimal Recognition Point, and evaluates "
     "comprehension outcomes across a range of reading speeds."),

    ("1. INTRODUCTION", True,
     "Traditional reading requires the eyes to move across a page in discrete "
     "jumps called saccades. Each saccade takes time and introduces a brief "
     "period of visual suppression during which information is not processed. "
     "Researchers in the 1970s proposed that presenting words at a fixed screen "
     "position could eliminate this overhead entirely."),

    ("2. METHODS", True,
     "Participants were recruited from a university subject pool. Each completed "
     "a baseline reading assessment followed by six weeks of daily RSVP training. "
     "Comprehension was measured using a validated multiple-choice instrument "
     "administered immediately after each session and at a one-week retention "
     "interval."),

    ("3. RESULTS", True,
     "Mean reading speed increased from 247 WPM at baseline to 389 WPM after "
     "training, a gain of 57 percent. Comprehension scores remained stable up "
     "to 350 WPM and declined moderately at higher speeds. Individual variation "
     "was substantial, with some participants reaching 500 WPM without "
     "significant comprehension loss."),

    ("4. DISCUSSION", True,
     "The data confirm that RSVP training produces durable speed gains. The "
     "comprehension plateau observed above 350 WPM is consistent with working "
     "memory constraints on sentence integration. Longer sentences and higher "
     "syntactic complexity were associated with greater comprehension loss at "
     "high speeds, suggesting that RSVP is most effective for expository prose."),

    ("5. CONCLUSION", True,
     "RSVP is an effective tool for increasing reading throughput when applied "
     "to appropriate text types. Comprehension remains robust at moderate "
     "training speeds. The technique is particularly well-suited to narrative "
     "and journalistic content; dense technical material benefits from slower "
     "pacing or a return to conventional reading for critical passages. "
     "Future work should examine long-term retention and transfer to untrained "
     "text types."),
]


def wrap(text, max_w, fname="helv", size=11):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).lstrip()
        if fitz.get_text_length(trial, fontname=fname, fontsize=size) < max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# build a flat list of (text, font_obj, size)
flat = []
for header, _, body in SECTIONS:
    flat.append((header, bold, 13))
    flat.append(("", font, 11))
    for ln in wrap(body, 495):
        flat.append((ln, font, 11))
    flat.append(("", font, 11))

# paginate (42 lines per page)
PER_PAGE = 42
pages = [flat[i:i + PER_PAGE] for i in range(0, len(flat), PER_PAGE)]

for page_lines in pages:
    page = doc.new_page(width=595, height=842)
    tw   = fitz.TextWriter(page.rect)
    y    = 60
    for text, fnt, size in page_lines:
        if text:
            tw.append((50, y), text, fontsize=size, font=fnt)
        y += size + 4
    tw.write_text(page)

out = "/data/test.pdf"
doc.save(out)
total = sum(len(b.split()) for _, _, b in SECTIONS)
print(f"Saved {out}  ({doc.page_count} pages, {total} body words, "
      f"{len(SECTIONS)} sections)")
