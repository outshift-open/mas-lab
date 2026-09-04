#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Example: Compare skill implementations across frameworks.

Shows how to instantiate and test different plugin implementations:
- Native (python-agentskills + python-sandbox)
- LangChain Deep Agents
- Google ADK
- LlamaIndex

Usage:
    # Test native implementation
    python examples/skill_plugin_comparison.py --impl native --skill-dir skills/

    # Test LangChain
    python examples/skill_plugin_comparison.py --impl langchain --skill-dir skills/

    # Test all implementations
    python examples/skill_plugin_comparison.py --impl all --skill-dir skills/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Setup logging
logging.basicConfig(
    format="[%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def compare_implementations(skill_dir: Path) -> None:
    """Compare all skill implementations on the same directory."""
    from mas.library.skills.plugins import (
        SkillImplementation,
        SkillPluginRegistry,
    )

    implementations = [
        SkillImplementation.NATIVE,
        SkillImplementation.LANGCHAIN,
        SkillImplementation.ADK,
        SkillImplementation.LLAMAINDEX,
    ]

    results = {}

    for impl in implementations:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {impl.value.upper()}")
        logger.info(f"{'='*60}")

        try:
            registry = SkillPluginRegistry(impl=impl)
            plugin = registry.get_plugin(base_dir=skill_dir)

            # Tier 1: Discover skills
            logger.info("Tier 1: Discovering skills...")
            skills = plugin.discover(skill_dir)
            logger.info(f"  Found {len(skills)} skills")

            results[impl.value] = {
                "status": "success",
                "skill_count": len(skills),
                "skills": list(skills.keys()),
                "activation": {},
                "execution": {},
            }

            # Tier 2 & 3: For each skill, test activation and execution
            for skill_name in list(skills.keys())[:1]:  # Test first skill only
                logger.info(f"\nTier 2: Activating skill '{skill_name}'...")
                try:
                    activation = plugin.activate(skill_name)
                    logger.info(
                        f"  Instructions length: {len(activation.body)} chars"
                    )
                    logger.info(f"  Resources: {list(activation.resources.keys())}")

                    results[impl.value]["activation"][skill_name] = {
                        "status": "success",
                        "instructions_length": len(activation.body),
                        "resources": list(activation.resources.keys()),
                    }
                except Exception as e:
                    logger.warning(f"  Activation failed: {e}")
                    results[impl.value]["activation"][skill_name] = {
                        "status": "error",
                        "error": str(e),
                    }

                # Tier 3: Try to list and read files
                logger.info(f"Tier 3: Listing skill resources...")
                try:
                    # Try to list scripts
                    script_dir = skills[skill_name].path / "scripts"
                    if script_dir.exists():
                        scripts = [f.name for f in script_dir.glob("*") if f.is_file()]
                        logger.info(f"  Found scripts: {scripts}")

                        if scripts:
                            first_script = scripts[0]
                            logger.info(f"  Reading script '{first_script}'...")
                            content = plugin.read_resource(
                                skill_name,
                                f"scripts/{first_script}",
                            )
                            logger.info(f"  Content length: {len(content)} chars")
                except Exception as e:
                    logger.warning(f"  Resource listing failed: {e}")

        except Exception as e:
            logger.error(f"Failed to test {impl.value}: {e}")
            results[impl.value] = {
                "status": "error",
                "error": str(e),
            }

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    print(json.dumps(results, indent=2, default=str))


def test_single_implementation(impl: str, skill_dir: Path) -> None:
    """Test a single skill implementation."""
    from mas.library.skills.plugins import (
        SkillImplementation,
        SkillPluginRegistry,
    )

    logger.info(f"Testing implementation: {impl}")
    logger.info(f"Skill directory: {skill_dir}")

    try:
        registry = SkillPluginRegistry(impl=impl)
        plugin = registry.get_plugin(base_dir=skill_dir)

        # Discover
        logger.info("\nDiscovering skills...")
        skills = plugin.discover(skill_dir)
        for name, meta in skills.items():
            logger.info(f"  - {name}: {meta.description}")

        # Test first skill
        if skills:
            first_skill = next(iter(skills.keys()))
            logger.info(f"\nActivating skill: {first_skill}")
            activation = plugin.activate(first_skill)
            logger.info(f"  Instructions (first 200 chars):")
            logger.info(f"  {activation.body[:200]}...")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare skill implementations across frameworks"
    )
    parser.add_argument(
        "--impl",
        choices=["native", "langchain", "adk", "llamaindex", "all"],
        default="native",
        help="Implementation to test",
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path("skills"),
        help="Root skill directory",
    )

    args = parser.parse_args()

    if not args.skill_dir.exists():
        logger.error(f"Skill directory not found: {args.skill_dir}")
        sys.exit(1)

    if args.impl == "all":
        compare_implementations(args.skill_dir)
    else:
        test_single_implementation(args.impl, args.skill_dir)


if __name__ == "__main__":
    main()
