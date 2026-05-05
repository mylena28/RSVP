"""Generate a test PDF with title, running headers, footnotes, and page numbers."""
import fitz

TITLE    = "The Mechanics of Speed Reading"
HEADER   = "Speed Reading Research — Internal Review"
FOOTNOTE = "1 Smith et al. (1974), Journal of Reading Research, vol. 12, pp. 45-67."
BODY = (
    "Rapid Serial Visual Presentation (RSVP) was first studied in laboratory "
    "settings during the 1970s, when psychologists began investigating the "
    "upper limits of human reading speed. The key insight was that the physical "
    "act of moving one's eyes across a line of text — a process called saccadic "
    "movement — consumes a measurable fraction of total reading time. "
    "By fixing the reader's gaze and moving the words instead, researchers "
    "observed immediate gains in measured words-per-minute without a corresponding "
    "drop in comprehension scores, at least at moderate speeds.\n\n"
    "The Optimal Recognition Point, sometimes abbreviated ORP, refers to the "
    "specific letter within a word at which the human visual system most "
    "efficiently begins to decode meaning. Empirical work places this point "
    "at approximately the second or third character for short words, shifting "
    "slightly rightward as word length increases. Aligning the ORP to a fixed "
    "horizontal position on screen eliminates the micro-adjustments the eye "
    "would otherwise make, further reducing cognitive overhead.\n\n"
    "Critics of RSVP note that it removes the reader's ability to regress — "
    "that is, to glance back at a phrase that was not fully understood on the "
    "first pass. Traditional silent reading relies heavily on regression; "
    "studies suggest skilled readers regress on roughly ten to fifteen percent "
    "of all words encountered. For narrative or expository prose the loss "
    "is minor, but for dense technical or legal text the inability to revisit "
    "a clause can meaningfully impair comprehension.\n\n"
    "Despite these limitations RSVP has found a devoted following among "
    "professionals who need to process large volumes of written material daily. "
    "Legal associates reviewing discovery documents, analysts scanning earnings "
    "reports, and researchers surveying literature have all reported productivity "
    "gains after adapting to the format. The consensus among practitioners is "
    "to start at a comfortable baseline — typically around 200 to 250 words per "
    "minute — and increase speed only when comprehension feels effortless at "
    "the current rate. Rushing the adaptation curve tends to produce frustration "
    "rather than improvement."
)

doc  = fitz.open()
font = fitz.Font("helv")

# wrap text to fit page width (495 pt usable)
words = BODY.split()
lines, cur = [], ""
for w in words:
    trial = (cur + " " + w).lstrip()
    if fitz.get_text_length(trial, fontname="helv", fontsize=11) < 495:
        cur = trial
    else:
        lines.append(cur)
        cur = w
if cur:
    lines.append(cur)

LINES_PER_PAGE = 30

for page_num in range(3):
    page = doc.new_page(width=595, height=842)
    tw   = fitz.TextWriter(page.rect)

    # running header (small, top of every page)
    tw.append((50, 28), HEADER, fontsize=8, font=font)
    # page number (small, bottom centre)
    tw.append((280, 822), str(page_num + 1), fontsize=8, font=font)

    y = 75
    if page_num == 0:
        tw.append((50, y), TITLE, fontsize=17, font=font)
        y += 35

    chunk = lines[page_num * LINES_PER_PAGE:(page_num + 1) * LINES_PER_PAGE]
    for ln in chunk:
        tw.append((50, y), ln, fontsize=11, font=font)
        y += 17

    # footnote on first page only (tiny font — extractor should filter it)
    if page_num == 0:
        tw.append((50, 800), FOOTNOTE, fontsize=7, font=font)

    tw.write_text(page)

out = "/data/test.pdf"
doc.save(out)
print(f"Saved {out}  ({doc.page_count} pages, {len(BODY.split())} body words)")
