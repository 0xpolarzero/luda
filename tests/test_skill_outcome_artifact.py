"""Freeze the accepted skill and its unchanged technical reference contracts."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/skill-outcomes"


class AcceptedSkillArtifact(unittest.TestCase):
    def test_exact_accepted_artifact_and_metadata(self):
        manifest = json.loads((FIXTURE / "accepted-artifact.json").read_text())
        data = (ROOT / "skills/luda/SKILL.md").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["skill_sha256"])
        self.assertEqual(len(data.decode("utf-8").split()), manifest["skill_words"])
        self.assertNotIn(b"\r", data)
        self.assertTrue(data.endswith(b"\n"))
        frontmatter = data.decode().split("---\n", 2)[1]
        fields = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
        self.assertEqual(set(fields), {"name", "description"})
        self.assertEqual(fields["name"], "luda")
        self.assertTrue(0 < len(fields["description"]) <= 1024)
        references = ROOT / "skills/luda/references"
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in references.glob("*.md")}, manifest["references"])
        self.assertEqual(len(manifest["references"]), 7)
        for target in re.findall(r"\]\((references/[^)]+)\)", data.decode()):
            self.assertTrue((ROOT / "skills/luda" / target).is_file(), target)

    def test_frozen_public_private_case_pairing(self):
        public = json.loads((FIXTURE / "public-cases.json").read_text())
        private = json.loads((FIXTURE / "evaluator-rubric.json").read_text())
        ids = [f"case-{i:02}" for i in range(1, 18)]
        self.assertEqual([c["id"] for c in public["cases"]], ids)
        self.assertEqual([c["id"] for c in private["cases"]], ids)
        for case in public["cases"]:
            self.assertEqual(set(case), {"id", "public_prompt"})
        for case in private["cases"]:
            self.assertTrue(case["required_semantics"])
            self.assertTrue(case["disqualifying_semantics"])
