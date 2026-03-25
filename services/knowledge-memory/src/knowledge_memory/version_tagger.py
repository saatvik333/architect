"""Simple utility to tag knowledge entries with version information.

Used to track which version of a library or framework a piece of
knowledge applies to, enabling version-aware retrieval.
"""

from __future__ import annotations

from architect_common.logging import get_logger
from knowledge_memory.models import KnowledgeEntry

logger = get_logger(component="knowledge_memory.version_tagger")


def tag_version(entry: KnowledgeEntry, version_tag: str) -> KnowledgeEntry:
    """Create a new KnowledgeEntry with the given version tag applied.

    Since KnowledgeEntry is frozen (immutable), this returns a new instance
    with the version_tag field updated.

    Args:
        entry: The knowledge entry to tag.
        version_tag: The version string to apply (e.g. "3.12", "v2.1.0").

    Returns:
        A new :class:`KnowledgeEntry` with the version tag set.
    """
    version_label = f"version:{version_tag}"
    new_tags = list(entry.tags)
    if version_label not in new_tags:
        new_tags.append(version_label)

    updated = entry.model_copy(
        update={
            "version_tag": version_tag,
            "tags": new_tags,
        }
    )
    logger.debug(
        "tagged entry with version",
        entry_id=str(entry.id),
        version_tag=version_tag,
    )
    return updated
