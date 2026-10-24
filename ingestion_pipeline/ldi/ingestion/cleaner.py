# Text cleaner for normalizing extracted document text
import re

def clean_text(text):
	# Remove extra whitespace and normalize line breaks
	text = re.sub(r'\s+', ' ', text)
	text = text.replace('\n', ' ').strip()
	return text
