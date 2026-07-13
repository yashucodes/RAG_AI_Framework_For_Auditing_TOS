# debug_clause_risk.py
#
# Purpose: Check what Gemini actually thinks about ONE specific clause,
# instead of guessing. Paste any clause below and run this to see its
# full reasoning -- category, confidence, WHY it decided that (reason),
# and the exact excerpt it would show the user.
#
# Run this from your project root: python debug_clause_risk.py

from app import classify_risk

# Paste the clause you want to check here:
clause = """
7.3 Who Is Responsible if Something Happens.
Our Service is provided "as is," and we can't guarantee it will be safe and
secure or will work perfectly all the time. TO THE EXTENT PERMITTED BY LAW,
WE ALSO DISCLAIM ALL WARRANTIES, WHETHER EXPRESS OR IMPLIED, INCLUDING THE
IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE,
TITLE, AND NON-INFRINGEMENT.
We also don't control what people and others do or say, and we aren't
responsible for their (or your) actions or conduct (whether online or
offline) or content (including unlawful or objectionable content). We also
aren't responsible for services and features offered by other people or
companies, even if you access them through our Service.
Our responsibility for anything that happens on the Service (also called
"liability") is limited as much as the law will allow. If there is an issue
with our Service, we can't know what all the possible impacts might be. You
agree that we won't be responsible ("liable") for any lost profits,
revenues, information, or data, or consequential, special, indirect,
exemplary, punitive, or incidental damages arising out of or related to
these Terms, even if we know they are possible. This includes when we
delete your content, information, or account.
"""

category, confidence, reason, excerpt = classify_risk(clause)

print(f"Category:   {category}")
print(f"Confidence: {confidence:.2f}")
print(f"Reason:     {reason}")
print(f"Excerpt:    {excerpt}")