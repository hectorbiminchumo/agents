from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from engineering_flow.tools.sandbox_tools import make_sandbox_tools


@CrewBase
class EngineeringCrew:
    """A self-contained engineering team (manager + 3 engineers) that builds one
    system inside its own sandbox directory. The Flow creates one instance of
    this crew per system, each pointed at a different sandbox, so several
    teams can build different systems in parallel without colliding.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, sandbox_dir: Path):
        self.sandbox_dir = Path(sandbox_dir)
        self._tools = make_sandbox_tools(self.sandbox_dir)

    @agent
    def backend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["backend_engineer"],
            verbose=True,
            tools=self._tools,
        )

    @agent
    def frontend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["frontend_engineer"],
            verbose=True,
            tools=self._tools,
        )

    @agent
    def test_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["test_engineer"],
            verbose=True,
            tools=self._tools,
        )

    @task
    def design_task(self) -> Task:
        return Task(config=self.tasks_config["design_task"])

    @task
    def code_task(self) -> Task:
        return Task(config=self.tasks_config["code_task"])

    @task
    def frontend_task(self) -> Task:
        return Task(config=self.tasks_config["frontend_task"])

    @task
    def test_task(self) -> Task:
        return Task(config=self.tasks_config["test_task"])

    @crew
    def crew(self) -> Crew:
        """Creates this team's crew, with its engineering_lead as manager_agent
        deciding how to delegate design/code/frontend/test work among the
        3 engineers — same hierarchical pattern as the single-team project.
        """
        manager = Agent(
            config=self.agents_config["engineering_lead"],
            verbose=True,
            allow_delegation=True,
        )

        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.hierarchical,
            manager_agent=manager,
            verbose=True,
        )
