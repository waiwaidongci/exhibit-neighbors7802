from enum import Enum
class Role(str,Enum):
    admin='admin'; analyst='analyst'; viewer='viewer'
class RunState(str,Enum):
    queued='queued'; running='running'; completed='completed'; failed='failed'
class ReviewState(str,Enum):
    draft='draft'; approved='approved'
class ComparisonVerdict(str,Enum):
    a_better='a_better'; b_better='b_better'; inconclusive='inconclusive'; infeasible='infeasible'
