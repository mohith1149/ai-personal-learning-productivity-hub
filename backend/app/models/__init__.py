"""Import every model so Base.metadata is complete (Alembic autogenerate relies on this)."""
from app.models.daily import (  # noqa: F401
    AIConversation,
    AIMessage,
    AIPendingAction,
    DailyCheckin,
    DailyCheckout,
    EmailNotification,
    WeeklyReport,
)
from app.models.habit import Habit, HabitLog  # noqa: F401
from app.models.planner import PlannerExcusal, RestDay  # noqa: F401
from app.models.learning import (  # noqa: F401
    Course,
    CourseLesson,
    CourseModule,
    LearningResource,
    LearningSession,
    RoadmapStage,
    RoadmapTopic,
    Video,
    VideoMembership,
    VideoPlaylist,
)
from app.models.project import (  # noqa: F401
    DailyChallenge,
    GitCommit,
    GitRepository,
    Project,
    ProjectIdea,
    ProjectMilestone,
    ProjectSession,
)
from app.models.task import RecurringTask, Task, TaskCategory  # noqa: F401
from app.models.user import ActivityLog, LoginAttempt, OAuthToken, User, UserSettings  # noqa: F401
