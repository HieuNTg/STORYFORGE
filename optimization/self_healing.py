"""
Self-Healing Pipeline System (Phase 4 - Module 3)
Auto-detect and fix issues: hallucination, logic contradictions, format errors
Strategy: Generate → Validate → Repair → Fallback
"""
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

class IssueType(Enum):
    HALLUCINATION = "hallucination"
    LOGIC_CONTRADICTION = "logic_contradiction"
    FORMAT_ERROR = "format_error"
    CHARACTER_INCONSISTENCY = "character_inconsistency"
    PLOT_HOLE = "plot_hole"

class SeverityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class DetectedIssue:
    issue_type: IssueType
    severity: SeverityLevel
    description: str
    location: str  # chapter/paragraph
    suggested_fix: Optional[str] = None
    confidence: float = 0.0
    detected_at: float = field(default_factory=time.time)

class SelfHealingPipeline:
    def __init__(self, llm_client=None, validation_rules: Optional[List] = None):
        self.llm_client = llm_client
        self.validation_rules = validation_rules or []
        
        # Issue tracking
        self.issues_history: List[DetectedIssue] = []
        self.auto_fixes_applied = 0
        self.fallbacks_triggered = 0
        
        # Stats
        self.stats = {
            "total_validations": 0,
            "issues_detected": 0,
            "auto_fixed": 0,
            "manual_review_needed": 0,
            "fallbacks": 0
        }
    
    async def validate_and_heal(self, content: str, context: Dict[str, Any],
                                chapter_id: str = "") -> Tuple[str, List[DetectedIssue]]:
        """
        Main healing pipeline:
        1. Validate content against rules
        2. Detect issues
        3. Auto-fix if possible
        4. Fallback to regeneration if critical
        """
        self.stats["total_validations"] += 1
        issues = await self._detect_issues(content, context, chapter_id)
        
        if not issues:
            return content, []
        
        self.stats["issues_detected"] += len(issues)
        self.issues_history.extend(issues)
        
        # Try auto-fix for non-critical issues
        fixable_issues = [i for i in issues if i.severity != SeverityLevel.CRITICAL]
        critical_issues = [i for i in issues if i.severity == SeverityLevel.CRITICAL]
        
        fixed_content = content
        if fixable_issues:
            fixed_content = await self._auto_fix(content, fixable_issues, context)
            self.stats["auto_fixed"] += len(fixable_issues)
            self.auto_fixes_applied += len(fixable_issues)
        
        # Handle critical issues with fallback
        if critical_issues:
            fixed_content = await self._fallback_regenerate(
                content, critical_issues, context
            )
            self.stats["fallbacks"] += 1
            self.fallbacks_triggered += 1
        
        # Log issues needing manual review
        unfixable = [i for i in issues if not i.suggested_fix]
        if unfixable:
            self.stats["manual_review_needed"] += len(unfixable)
        
        return fixed_content, issues
    
    async def _detect_issues(self, content: str, context: Dict[str, Any],
                            chapter_id: str) -> List[DetectedIssue]:
        """Detect various types of issues"""
        issues = []
        
        # 1. Format validation
        format_issues = self._check_format(content, chapter_id)
        issues.extend(format_issues)
        
        # 2. Character consistency check
        char_issues = await self._check_character_consistency(content, context, chapter_id)
        issues.extend(char_issues)
        
        # 3. Logic contradiction detection
        logic_issues = await self._check_logic_contradictions(content, context, chapter_id)
        issues.extend(logic_issues)
        
        # 4. Hallucination detection (using LLM)
        if self.llm_client:
            hallu_issues = await self._check_hallucination(content, context, chapter_id)
            issues.extend(hallu_issues)
        
        return issues
    
    def _check_format(self, content: str, chapter_id: str) -> List[DetectedIssue]:
        """Check for formatting errors"""
        issues = []
        
        # Check for incomplete sentences
        if content.strip() and not content.strip().endswith(('.', '!', '?', '"')):
            issues.append(DetectedIssue(
                issue_type=IssueType.FORMAT_ERROR,
                severity=SeverityLevel.LOW,
                description="Content ends without proper punctuation",
                location=f"Chapter {chapter_id}",
                suggested_fix="Add appropriate ending punctuation",
                confidence=0.9
            ))
        
        # Check for unclosed quotes
        quote_count = content.count('"')
        if quote_count % 2 != 0:
            issues.append(DetectedIssue(
                issue_type=IssueType.FORMAT_ERROR,
                severity=SeverityLevel.MEDIUM,
                description="Unclosed quotation marks detected",
                location=f"Chapter {chapter_id}",
                suggested_fix="Close all quotation marks",
                confidence=0.95
            ))
        
        return issues
    
    async def _check_character_consistency(self, content: str, 
                                          context: Dict[str, Any],
                                          chapter_id: str) -> List[DetectedIssue]:
        """Check for character inconsistencies"""
        issues = []
        characters = context.get("core", {}).get("characters", {})
        
        if not characters:
            return issues
        
        # Check if character names are used consistently
        for char_name in characters.keys():
            if char_name.lower() in content.lower():
                # Mock: In production, verify traits/actions match character profile
                pass
        
        return issues
    
    async def _check_logic_contradictions(self, content: str,
                                         context: Dict[str, Any],
                                         chapter_id: str) -> List[DetectedIssue]:
        """Check for logical contradictions with previous chapters"""
        issues = []
        
        # Mock implementation
        # In production: compare events/timeline with previous chapters
        
        return issues
    
    async def _check_hallucination(self, content: str,
                                  context: Dict[str, Any],
                                  chapter_id: str) -> List[DetectedIssue]:
        """Use LLM to detect potential hallucinations"""
        issues = []
        
        if not self.llm_client:
            return issues
        
        # Prompt LLM to verify facts against context
        # Mock: In production, call LLM with context + content
        
        return issues
    
    async def _auto_fix(self, content: str, issues: List[DetectedIssue],
                       context: Dict[str, Any]) -> str:
        """Attempt to automatically fix detected issues"""
        fixed_content = content
        
        for issue in issues:
            if issue.issue_type == IssueType.FORMAT_ERROR:
                if "punctuation" in issue.description.lower():
                    fixed_content = fixed_content.rstrip() + "."
                elif "quotation" in issue.description.lower():
                    fixed_content = fixed_content + '"'
            
            elif issue.suggested_fix and self.llm_client:
                # Use LLM to apply suggested fix
                # Mock: In production, call LLM with fix instruction
                pass
        
        return fixed_content
    
    async def _fallback_regenerate(self, content: str, 
                                   critical_issues: List[DetectedIssue],
                                   context: Dict[str, Any]) -> str:
        """Regenerate content when critical issues detected"""
        if not self.llm_client:
            return content  # Can't regenerate without LLM
        
        # Build regeneration prompt with constraints
        # Mock: In production, call LLM with context + constraints
        
        # For now, return original with warning comment
        return content + "\n[WARNING: Critical issues detected, manual review recommended]"
    
    def get_stats(self) -> Dict[str, Any]:
        """Return healing statistics"""
        total = self.stats["total_validations"] or 1
        return {
            "validations": self.stats["total_validations"],
            "issues_detected": self.stats["issues_detected"],
            "auto_fix_rate": round(self.stats["auto_fixed"] / max(self.stats["issues_detected"], 1) * 100, 2),
            "fallback_rate": round(self.stats["fallbacks"] / total * 100, 2),
            "manual_review_count": self.stats["manual_review_needed"],
            "total_auto_fixes": self.auto_fixes_applied,
            "total_fallbacks": self.fallbacks_triggered
        }

if __name__ == "__main__":
    healer = SelfHealingPipeline()
    print("✓ SelfHealingPipeline initialized successfully")
