from backend.app.core.database import SessionLocal
from database.models.ArticleData import Article
from database.models.ChatMessage import ChatMessage
from database.models.ChatSession import ChatSession
from sqlalchemy import update

class DbFunctions:
    @staticmethod
    def get_chatsessions(userid, lim=1000):
        db = SessionLocal()
        try:
            messages = db.query(ChatSession)\
                    .filter(ChatSession.user_id == userid)\
                    .limit(lim)\
                    .all()
            return messages
        except Exception as e:
            print(f"Error getting chat sessions for user {userid}: {str(e)}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_chatmessages(chatid, lim=1000):
        db = SessionLocal()
        try:
            messages = db.query(ChatMessage)\
                    .filter(ChatMessage.chat_id == chatid)\
                    .limit(lim)\
                    .all()
            return messages
        except Exception as e:
            print(f"Error getting chat messages for chat {chatid}: {str(e)}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_articles(lim=1000):
        db = SessionLocal()
        try:
            articles = db.query(Article)\
                    .filter(Article.abstract_text.isnot(None))\
                    .filter(Article.title.isnot(None))\
                    .limit(lim)\
                    .all()
            return articles
        except Exception as e:
            print(f"Error getting articles: {str(e)}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_articles_with_embedding(lim=1000):
        db = SessionLocal()
        try:
            articles = db.query(Article)\
                    .filter(Article.abstract_text.isnot(None))\
                    .filter(Article.title.isnot(None))\
                    .filter(Article.embedding.isnot(None))\
                    .limit(lim)\
                    .all()
            return articles
        except Exception as e:
            print(f"Error getting articles: {str(e)}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_articles_for_embedding(lim=1000):
        """
        Embedding null olan satirlardan getirir. embedding uretim islemi icin.
        """
        db = SessionLocal()
        try:
            articles = db.query(Article)\
                    .filter(Article.abstract_text.isnot(None))\
                    .filter(Article.title.isnot(None))\
                    .filter(Article.embedding.is_(None))\
                    .limit(lim)\
                    .all()
            return articles
        except Exception as e:
            print(f"Error getting articles: {str(e)}")
            return []
        finally:
            db.close()

    @staticmethod
    def update_embedding(articleid, emb):
        db = SessionLocal()
        try:
            result = db.execute(
                update(Article)
                .where(Article.id == articleid)
                .values(embedding = emb)
            )
            db.commit()
            return result.rowcount > 0
        except Exception as e:
            db.rollback()
            print(f"Error updating embedding for article {articleid}: {str(e)}")
            return False
        finally:
            db.close()

if __name__ == '__main__':
    # DbFunctions.get_articles(2000)
    DbFunctions.get_chatmessages(1, 2000)
