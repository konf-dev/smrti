# Integration test package initialization

import pytest
import asyncio
from typing import Dict, Any, List

# Common fixtures and utilities for integration tests


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def integration_test_cleanup():
    """Fixture to track and cleanup resources in integration tests."""
    cleanup_tasks = []
    
    def register_cleanup(coro):
        """Register a cleanup coroutine to be called during teardown."""
        cleanup_tasks.append(coro)
    
    yield register_cleanup
    
    # Run all cleanup tasks
    for cleanup_coro in reversed(cleanup_tasks):  # Reverse order for proper cleanup
        try:
            await cleanup_coro()
        except Exception as e:
            # Log cleanup errors but don't fail the test
            print(f"Cleanup error: {e}")


class IntegrationTestHelper:
    """Helper class for integration test utilities."""
    
    @staticmethod
    async def wait_for_condition(condition_func, timeout=5.0, interval=0.1):
        """Wait for a condition to become true within timeout."""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await condition_func():
                return True
            await asyncio.sleep(interval)
        
        return False
    
    @staticmethod
    def assert_memory_fields(record, expected_fields):
        """Assert that a memory record has all expected fields."""
        for field, expected_value in expected_fields.items():
            if field == "content_text":
                actual_value = record.content.get_text()
            elif field.startswith("metadata."):
                metadata_key = field.split(".", 1)[1]
                actual_value = record.metadata.get(metadata_key)
            else:
                actual_value = getattr(record, field, None)
            
            assert actual_value == expected_value, f"Field {field}: expected {expected_value}, got {actual_value}"
    
    @staticmethod
    def create_test_scenario(name: str, description: str, steps: List[Dict[str, Any]]):
        """Create a structured test scenario."""
        return {
            "name": name,
            "description": description,
            "steps": steps,
            "metadata": {
                "created_at": "test_time",
                "test_type": "integration"
            }
        }


# Common test data generators
def generate_test_memories(count: int, prefix: str = "test") -> List[Dict[str, Any]]:
    """Generate test memory data."""
    memories = []
    for i in range(count):
        memories.append({
            "text": f"{prefix} memory {i + 1} with some content",
            "metadata": {
                "index": i + 1,
                "category": prefix,
                "generated": True
            }
        })
    return memories


def generate_user_scenarios() -> Dict[str, Dict[str, Any]]:
    """Generate realistic user scenario data."""
    return {
        "developer": {
            "work_context": [
                "Working on microservices architecture migration",
                "Debugging database performance issues",
                "Code review for authentication service"
            ],
            "learning_context": [
                "Learning Kubernetes orchestration patterns",
                "Studying distributed system design principles",
                "Reading about event-driven architecture"
            ]
        },
        "researcher": {
            "research_context": [
                "Analyzing climate change impact on agriculture",
                "Reviewing machine learning papers for methodology",
                "Collecting data on renewable energy adoption"
            ],
            "collaboration_context": [
                "Coordinating with international research team",
                "Preparing presentation for climate conference",
                "Writing grant proposal for continued funding"
            ]
        },
        "student": {
            "academic_context": [
                "Studying for computer science algorithms exam",
                "Working on senior capstone project",
                "Attending office hours for data structures"
            ],
            "personal_context": [
                "Planning internship applications for summer",
                "Organizing study group for final exams",
                "Balancing coursework with part-time job"
            ]
        }
    }