"""
RecallAI - Test Results Viewer
Display and analyze test_results.json in a readable format
"""

import json
import sys
from typing import Dict, List


def load_results() -> Dict:
    """Load test_results.json"""
    try:
        with open("test_results.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Error: test_results.json not found")
        print("   Run run_tests.py first to generate test results")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in test_results.json: {e}")
        sys.exit(1)


def display_summary(data: Dict):
    """Display overall test summary"""
    print("=" * 70)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 70)
    
    if "timestamp" in data:
        print(f"\nGenerated: {data['timestamp']}")
    
    total = data.get("total_tests", 0)
    passed = data.get("total_passed", 0)
    failed = data.get("total_failed", 0)
    pass_rate = data.get("overall_pass_rate", 0)
    
    print(f"\n📈 Overall Results:")
    print(f"   Total Tests: {total}")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📊 Pass Rate: {pass_rate:.1f}%")
    
    # Validation vs LLM breakdown
    val_passed = data.get("validation_passed", 0)
    val_failed = data.get("validation_failed", 0)
    llm_passed = data.get("llm_passed", 0)
    llm_failed = data.get("llm_failed", 0)
    
    if val_passed + val_failed > 0:
        val_rate = (val_passed / (val_passed + val_failed) * 100) if (val_passed + val_failed) > 0 else 0
        print(f"\n🔒 Validation & Safety Tests:")
        print(f"   ✅ Passed: {val_passed}")
        print(f"   ❌ Failed: {val_failed}")
        print(f"   📊 Pass Rate: {val_rate:.1f}%")
    
    if llm_passed + llm_failed > 0:
        llm_rate = (llm_passed / (llm_passed + llm_failed) * 100) if (llm_passed + llm_failed) > 0 else 0
        print(f"\n🤖 LLM Tests (Summary & Quiz):")
        print(f"   ✅ Passed: {llm_passed}")
        print(f"   ❌ Failed: {llm_failed}")
        print(f"   📊 Pass Rate: {llm_rate:.1f}%")


def display_by_category(data: Dict):
    """Display results grouped by category"""
    results = data.get("results", [])
    
    if not results:
        print("\n⚠️  No test results found")
        return
    
    print("\n" + "=" * 70)
    print("📋 RESULTS BY CATEGORY")
    print("=" * 70)
    
    categories = {}
    for result in results:
        cat = result.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"passed": [], "failed": []}
        
        if result.get("status") == "PASS":
            categories[cat]["passed"].append(result)
        else:
            categories[cat]["failed"].append(result)
    
    for cat in sorted(categories.keys()):
        stats = categories[cat]
        total = len(stats["passed"]) + len(stats["failed"])
        passed_count = len(stats["passed"])
        rate = (passed_count / total * 100) if total > 0 else 0
        
        print(f"\n📁 {cat.upper()}: {passed_count}/{total} passed ({rate:.1f}%)")
        
        if stats["failed"]:
            print(f"   ❌ Failed Tests:")
            for result in stats["failed"]:
                test_id = result.get("id", "?")
                status = result.get("status", "UNKNOWN")
                error = result.get("error", "")
                response = result.get("response", "")
                
                print(f"      - Test {test_id} ({status})")
                if error:
                    print(f"        Error: {error[:60]}...")
                if response:
                    print(f"        Response: {response[:60]}...")


def display_failed_tests(data: Dict):
    """Display detailed information about failed tests"""
    results = data.get("results", [])
    failed = [r for r in results if r.get("status") != "PASS"]
    
    if not failed:
        print("\n✅ No failed tests!")
        return
    
    print("\n" + "=" * 70)
    print(f"❌ FAILED TESTS DETAIL ({len(failed)} total)")
    print("=" * 70)
    
    # Load test definitions
    try:
        with open("tests.json", "r") as f:
            tests = json.load(f)
        test_map = {t["id"]: t for t in tests}
    except:
        test_map = {}
    
    for result in failed:
        test_id = result.get("id", "?")
        category = result.get("category", "unknown")
        status = result.get("status", "UNKNOWN")
        
        test_def = test_map.get(test_id, {})
        description = test_def.get("description", "No description")
        expected = test_def.get("expected_pattern", "")
        input_text = test_def.get("input", "")
        
        print(f"\n{'─' * 70}")
        print(f"🧪 Test {test_id}: {category} ({status})")
        print(f"   Description: {description}")
        if input_text:
            print(f"   Input: {input_text[:80]}{'...' if len(input_text) > 80 else ''}")
        if expected:
            print(f"   Expected Pattern: {expected}")
        
        if "error" in result:
            print(f"   ❌ Error: {result['error']}")
        if "response" in result:
            resp = result["response"]
            if resp:
                print(f"   📝 Response: {resp[:100]}{'...' if len(str(resp)) > 100 else ''}")
        if "latency_ms" in result:
            print(f"   ⏱️  Latency: {result['latency_ms']}ms")


def display_all_results(data: Dict):
    """Display all test results in a table format"""
    results = data.get("results", [])
    
    if not results:
        return
    
    print("\n" + "=" * 70)
    print("📋 ALL TEST RESULTS")
    print("=" * 70)
    
    # Sort by test ID
    sorted_results = sorted(results, key=lambda x: x.get("id", 0))
    
    print(f"\n{'ID':<5} {'Status':<10} {'Category':<15} {'Details':<40}")
    print("─" * 70)
    
    for result in sorted_results:
        test_id = result.get("id", "?")
        status = result.get("status", "UNKNOWN")
        category = result.get("category", "unknown")
        
        details = ""
        if "latency_ms" in result:
            details = f"{result['latency_ms']}ms"
        elif "error" in result:
            details = result["error"][:35] + "..." if len(result["error"]) > 35 else result["error"]
        
        status_icon = "✅" if status == "PASS" else "❌"
        print(f"{test_id:<5} {status_icon} {status:<8} {category:<15} {details:<40}")


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    else:
        mode = "summary"
    
    data = load_results()
    
    if mode == "summary" or mode == "all":
        display_summary(data)
    
    if mode == "category" or mode == "all":
        display_by_category(data)
    
    if mode == "failed" or mode == "all":
        display_failed_tests(data)
    
    if mode == "table" or mode == "all":
        display_all_results(data)
    
    if mode not in ["summary", "category", "failed", "table", "all"]:
        print(f"Usage: python view_test_results.py [summary|category|failed|table|all]")
        print("\nModes:")
        print("  summary  - Overall statistics (default)")
        print("  category - Results grouped by category")
        print("  failed   - Detailed info about failed tests")
        print("  table    - All results in table format")
        print("  all      - Show everything")


if __name__ == "__main__":
    main()
