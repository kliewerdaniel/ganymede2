"""Create a test corpus for Phase 2 verification."""

from pathlib import Path


def create_test_corpus(corpus_dir: str):
    """Create a small test corpus with sample sources."""
    corpus_path = Path(corpus_dir)
    corpus_path.mkdir(parents=True, exist_ok=True)

    # Sample document 1: a short biography
    doc1 = corpus_path / "chris_bio.txt"
    doc1.write_text("""Christopher James Kliewer was born on March 15, 1985, in Seattle, Washington. He grew up in the Pacific Northwest with his brother Daniel. Chris was known for his sharp wit and his ability to make friends wherever he went.

He attended the University of Washington, where he studied computer science. Chris was an avid hiker and loved the outdoors. He spent many weekends exploring the Cascade Mountains.

After college, Chris worked as a software engineer at several tech companies in Seattle. He was passionate about open-source software and contributed to several projects. His colleagues remembered him for his collaborative spirit and his willingness to help others.

Chris was not just a software engineer. He was a musician who played guitar and wrote songs. He performed at local venues in Seattle and had a small but dedicated following. His music was influenced by folk and indie rock.

In his personal life, Chris was known for his loyalty to his friends and family. He was always there for the people he cared about. His brother Daniel was his closest friend and confidant.

Chris passed away on September 12, 2024, after a brief illness. He was 39 years old. He is survived by his brother Daniel, his parents, and many friends who loved him.""")

    # Sample document 2: a conversation
    doc2 = corpus_path / "conversation.txt"
    doc2.write_text("""Daniel: Hey Chris, how's the new project going?

Chris: It's going well. We're making good progress on the open-source compiler.

Daniel: That's great. Are you still planning to present at the meetup next week?

Chris: Yes, I'm preparing the slides now. I think people will find it interesting.

Daniel: I'm sure they will. Your work on deterministic extraction is really innovative.

Chris: Thanks. I'm excited to share it. The key insight is that most of the work can be done at compile time.

Daniel: That makes sense. It's like what you did with the knowledge graph project.

Chris: Exactly. The same principles apply. Compile once, query many times.

Daniel: Are you still hiking on weekends?

Chris: When I can. The Cascades are beautiful this time of year.

Daniel: We should plan a trip together.

Chris: I'd like that. Let's do it next month.""")

    # Sample document 3: a Reddit-style post
    doc3 = corpus_path / "reddit_post.txt"
    doc3.write_text("""title: My brother passed away and I'm building a knowledge graph to remember him

body: My brother Chris passed away recently. He was a software engineer, a musician, and one of the kindest people I've ever known.

I'm building a knowledge graph to capture what I remember about him. Not to replace him — nothing could do that — but to have a structured record of who he was.

The system ingests documents, extracts claims, and builds a graph of relationships. It's deterministic, so the same inputs always produce the same outputs.

I'm calling it Ganymede, after the moon of Jupiter. Chris loved astronomy.

If anyone has built something similar, I'd love to hear about it. This is both a technical project and a personal one.

Edit: Thank you for the kind messages. Chris would have appreciated the support.""")

    return [str(doc1), str(doc2), str(doc3)]
