"""Frozen lexical guards; no laboratory dependency at runtime."""
import re
import unicodedata
from app.captions.terminology_normalizer import _edit_distance as edit_distance

TOKEN = re.compile(r"\d+(?:[.,:/]\d+)*|[^\W\d_]+(?:'[^\W\d_]+)*", re.UNICODE)

NEGATIONS = set("no not never without neither nor denies denied negative absence absent cannot unlikely".split())

NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand half quarter first second third".split())

UNITS = set("mg mcg µg μg g kg ml l mmhg mmol mol bpm hz percent percentage milligram milligrams microgram micrograms milliliter milliliters millimetres millimeters mercury".split())

MEASUREMENT=re.compile(r"[<>≤≥]?\s*[+−-]?\d+(?:[.,:/]\d+)*(?:\s*(?:mmol/l|mmhg|mcg|µg|μg|mg|kg|ml|bpm|%|g|l)\b|\s*%)?",re.I)

def measurement_signatures(text):
    """Literal review channel: catches signs/percent omitted by lexical WER.

    Formatting or spoken/digit differences can also trigger it. Not a semantic
    equivalence checker, dose validator or certified medical-error count.
    """
    text=unicodedata.normalize('NFKC',text).casefold().replace('−','-')
    return [{'value':re.sub(r'\s+','',m.group()),'start':m.start(),'end':m.end()} for m in MEASUREMENT.finditer(text)]

def tokens(text):
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'").replace("‘", "'")
    return TOKEN.findall(text)
