# models.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import JSONB
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    role = Column(String, nullable=False)  # admin, teacher, student
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)

    group = relationship("Group", back_populates="students")
    poll_progress = relationship("UserPollProgress", back_populates="user")


class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    students = relationship("User", back_populates="group")


class Poll(Base):
    __tablename__ = 'polls'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'))
    target_role = Column(String, nullable=False)  # teacher, student, all
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    questions = relationship("Question", back_populates="poll")


class Question(Base):
    __tablename__ = 'questions'

    id = Column(Integer, primary_key=True)
    poll_id = Column(Integer, ForeignKey('polls.id'))
    text = Column(Text, nullable=False)

    poll = relationship("Poll", back_populates="questions")
    answers = relationship("Answer", back_populates="question")


class Answer(Base):
    __tablename__ = 'answers'

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    answer_text = Column(Text, nullable=False)

    question = relationship("Question", back_populates="answers")


class UserPollProgress(Base):
    __tablename__ = 'user_poll_progress'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    poll_id = Column(Integer, ForeignKey('polls.id'))
    is_completed = Column(Boolean, default=False)
    last_question_id = Column(Integer, ForeignKey('questions.id'), nullable=True)

    user = relationship("User", back_populates="poll_progress")

class UserAnswer(Base):
    __tablename__ = 'user_answers'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    answer_text = Column(String, nullable=False)

    user = relationship("User")
    question = relationship("Question")
