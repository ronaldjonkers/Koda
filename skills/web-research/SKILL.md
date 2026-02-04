---
name: web-research
description: Research topics online, gather information, compare products, find answers
triggers: research, zoek op, find out, look up, compare, onderzoek, wat is, how does
priority: 8
---

# Web Research Skill

You are conducting web research. Follow this systematic approach.

## Research Process

### 1. Understand the Query
- What specific information is needed?
- What type of sources are most relevant?
- What's the scope (quick answer vs deep research)?

### 2. Search Strategy
Use multiple search approaches:

```
1. ddg_search - General web search (free, no API key)
2. web_search - Brave Search (better results if API key configured)
3. wikipedia - For factual/encyclopedic info
4. web_fetch - To read full articles
```

### 3. Search Tips
- Use specific keywords, not full sentences
- Try different phrasings if first search fails
- For Dutch topics, try both Dutch and English queries
- For recent events, include year in query

### 4. Verify Information
- Cross-reference multiple sources
- Prefer official/authoritative sources
- Note when information might be outdated
- Be skeptical of single-source claims

### 5. Synthesize Results
- Summarize key findings clearly
- Cite sources when relevant
- Acknowledge uncertainty
- Suggest follow-up research if needed

## Common Research Types

### Product Research
1. Search for "[product] review"
2. Compare specs from official sites
3. Check multiple review sources
4. Summarize pros/cons

### Technical Information
1. Check official documentation first
2. Search Stack Overflow for code issues
3. Look for tutorials/guides
4. Verify version compatibility

### News/Events
1. Search recent news
2. Check multiple news sources
3. Note publication dates
4. Distinguish facts from opinions

### Price Comparison
1. Search multiple retailers
2. Note shipping costs
3. Check for deals/coupons
4. Compare warranties

## Output Format

For research results:
```
## Summary
[Brief answer to the query]

## Key Findings
- Finding 1 (Source: ...)
- Finding 2 (Source: ...)

## Details
[More detailed information if needed]

## Sources
1. [Source name/URL]
2. [Source name/URL]
```

## When Research Fails
- Explain what you searched for
- Suggest alternative approaches
- Ask user for more specific criteria
