#!/usr/bin/env python3
"""
run_tests.py - Comprehensive test runner for Smrti

Runs the complete test suite with proper reporting and coverage.
"""

import asyncio
import sys
import os
from pathlib import Path
import subprocess
from typing import Dict, List, Any, Optional

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


class TestRunner:
    """Comprehensive test runner for the Smrti project."""
    
    def __init__(self):
        self.project_root = project_root
        self.test_results = {}
        self.coverage_results = {}
    
    def run_unit_tests(self) -> Dict[str, Any]:
        """Run unit tests with coverage."""
        print("🧪 Running unit tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/unit/",
            "-v",
            "--tb=short",
            "--cov=smrti",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov/unit",
            "--junit-xml=test-results/unit-results.xml",
            "--asyncio-mode=auto"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    
    def run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests."""
        print("🔗 Running integration tests...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/integration/",
            "-v",
            "--tb=short",
            "--cov=smrti",
            "--cov-append",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov/integration",
            "--junit-xml=test-results/integration-results.xml",
            "--asyncio-mode=auto"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run complete test suite."""
        print("🚀 Running complete test suite...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            "tests/",
            "-v",
            "--tb=short",
            "--cov=smrti", 
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov/complete",
            "--cov-report=xml:coverage.xml",
            "--junit-xml=test-results/complete-results.xml",
            "--asyncio-mode=auto"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    
    def run_specific_test(self, test_path: str) -> Dict[str, Any]:
        """Run a specific test file or test."""
        print(f"🎯 Running specific test: {test_path}")
        
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            "-v",
            "--tb=long",
            "--asyncio-mode=auto"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    
    def check_test_dependencies(self) -> List[str]:
        """Check if all test dependencies are available."""
        missing_deps = []
        
        try:
            import pytest
        except ImportError:
            missing_deps.append("pytest")
        
        try:
            import pytest_cov
        except ImportError:
            missing_deps.append("pytest-cov")
        
        try:
            import pytest_asyncio
        except ImportError:
            missing_deps.append("pytest-asyncio")
        
        return missing_deps
    
    def setup_test_environment(self):
        """Set up test environment and directories."""
        # Create test result directories
        test_results_dir = self.project_root / "test-results"
        htmlcov_dir = self.project_root / "htmlcov"
        
        test_results_dir.mkdir(exist_ok=True)
        htmlcov_dir.mkdir(exist_ok=True)
        
        # Set environment variables for testing
        os.environ["SMRTI_TESTING"] = "true"
        os.environ["PYTHONPATH"] = str(self.project_root)
    
    def generate_test_report(self, results: Dict[str, Any]):
        """Generate a comprehensive test report."""
        print("\n" + "="*60)
        print("📊 TEST REPORT")
        print("="*60)
        
        for test_type, result in results.items():
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            print(f"{test_type.upper()}: {status}")
            
            if not result["success"]:
                print(f"  Error output:\n{result['stderr']}")
        
        print("="*60)
        
        # Coverage information
        coverage_files = list(self.project_root.glob("htmlcov/*/index.html"))
        if coverage_files:
            print("📈 Coverage reports generated:")
            for coverage_file in coverage_files:
                print(f"  - {coverage_file}")
        
        # Test result files
        result_files = list((self.project_root / "test-results").glob("*.xml"))
        if result_files:
            print("📋 Test result files:")
            for result_file in result_files:
                print(f"  - {result_file}")
    
    def run_linting(self) -> Dict[str, Any]:
        """Run code linting checks."""
        print("🔍 Running code linting...")
        
        # Check if flake8 is available
        try:
            cmd = [sys.executable, "-m", "flake8", "smrti/", "--max-line-length=100"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
                "available": True
            }
        except FileNotFoundError:
            return {
                "available": False,
                "success": True,  # Don't fail if linting not available
                "message": "flake8 not available"
            }
    
    def run_type_checking(self) -> Dict[str, Any]:
        """Run type checking with mypy."""
        print("🔎 Running type checking...")
        
        try:
            cmd = [sys.executable, "-m", "mypy", "smrti/", "--ignore-missing-imports"]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
                "available": True
            }
        except FileNotFoundError:
            return {
                "available": False,
                "success": True,  # Don't fail if mypy not available
                "message": "mypy not available"
            }


def main():
    """Main test runner entry point."""
    runner = TestRunner()
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "unit":
            runner.setup_test_environment()
            result = runner.run_unit_tests()
            print(result["stdout"])
            sys.exit(0 if result["success"] else 1)
            
        elif command == "integration":
            runner.setup_test_environment()
            result = runner.run_integration_tests()
            print(result["stdout"])
            sys.exit(0 if result["success"] else 1)
            
        elif command == "lint":
            result = runner.run_linting()
            if result["available"]:
                print(result["stdout"])
                print(result["stderr"])
                sys.exit(0 if result["success"] else 1)
            else:
                print("Linting not available")
                sys.exit(0)
                
        elif command == "type-check":
            result = runner.run_type_checking()
            if result["available"]:
                print(result["stdout"])
                print(result["stderr"])
                sys.exit(0 if result["success"] else 1)
            else:
                print("Type checking not available")
                sys.exit(0)
                
        elif command.startswith("tests/"):
            runner.setup_test_environment()
            result = runner.run_specific_test(command)
            print(result["stdout"])
            sys.exit(0 if result["success"] else 1)
            
        else:
            print(f"Unknown command: {command}")
            print("Available commands: unit, integration, lint, type-check, tests/<path>")
            sys.exit(1)
    
    # Run complete test suite
    print("🎉 Starting Smrti Test Suite")
    print("="*50)
    
    # Check dependencies
    missing_deps = runner.check_test_dependencies()
    if missing_deps:
        print(f"❌ Missing test dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install pytest pytest-cov pytest-asyncio")
        sys.exit(1)
    
    # Set up environment
    runner.setup_test_environment()
    
    # Run all test suites
    results = {}
    
    # Code quality checks
    results["linting"] = runner.run_linting()
    results["type_checking"] = runner.run_type_checking()
    
    # Unit tests
    results["unit_tests"] = runner.run_unit_tests()
    
    # Integration tests
    if results["unit_tests"]["success"]:
        results["integration_tests"] = runner.run_integration_tests()
    else:
        print("⚠️  Skipping integration tests due to unit test failures")
        results["integration_tests"] = {"success": False, "skipped": True}
    
    # Complete test suite (for full coverage report)
    if all(result.get("success", False) for result in results.values()):
        print("🎯 All tests passed! Generating complete coverage report...")
        results["complete_suite"] = runner.run_all_tests()
    
    # Generate report
    runner.generate_test_report(results)
    
    # Exit with appropriate code
    all_success = all(result.get("success", False) for result in results.values())
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()