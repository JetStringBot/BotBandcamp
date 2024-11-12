import praw
import configparser
import csv
import os
from datetime import datetime
import logging
import time

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Construct the absolute path to the config.ini file
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, 'config.ini')

# Read the configuration file with interpolation disabled
config = configparser.ConfigParser(interpolation=None)
config.read(config_path)

# Set up your Reddit client using the config file
reddit = praw.Reddit(
    client_id=config['reddit']['client_id'],
    client_secret=config['reddit']['client_secret'],
    user_agent=config['reddit']['user_agent'],
    username=config['reddit']['username'],
    password=config['reddit']['password']
)

# Define the subreddit to monitor
subreddit_name = 'TestBandcampBot'
subreddit = reddit.subreddit(subreddit_name)

# Log the subreddit being monitored
logging.info(f"Monitoring subreddit: {subreddit.display_name}")

# Path to the flat file in the same directory
file_path = 'user_activity.csv'

# Minimum word count and reply threshold
MIN_WORD_COUNT = 150
MIN_REPLIES = 5

def initialize_file():
    if not os.path.exists(file_path):
        logging.debug("Initializing the file...")
        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['username', 'comment_count', 'last_post_date'])

def read_user_activity():
    logging.debug("Reading user activity...")
    user_activity = {}
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            user_activity[row['username']] = {
                'comment_count': int(row['comment_count']),
                'last_post_date': row['last_post_date']
            }
    return user_activity

def update_user_activity(username, comment_count, last_post_date):
    logging.debug(f"Updating activity for user: {username}")
    user_activity = read_user_activity()
    user_activity[username] = {
        'comment_count': comment_count,
        'last_post_date': last_post_date
    }
    with open(file_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['username', 'comment_count', 'last_post_date'])
        for user, activity in user_activity.items():
            writer.writerow([user, activity['comment_count'], activity['last_post_date']])

def count_words(text):
    return len(text.split())

def get_user_comments(user, limit=100):
    logging.debug(f"Fetching comments for user: {user.name} from subreddit: {subreddit.display_name}")
    comments = list(user.comments.new(limit=limit))
    subreddit_comments = [comment for comment in comments if comment.subreddit.display_name == subreddit_name]
    return subreddit_comments

def check_user_eligibility(user):
    logging.debug(f"Checking eligibility for user: {user.name}")
    comments = get_user_comments(user)
    valid_comments = []
    for comment in comments:
        logging.debug(f"Evaluating comment: {comment.body}")
        if count_words(comment.body) >= MIN_WORD_COUNT:
            logging.debug("Comment is valid and counts towards eligibility.")
            valid_comments.append(comment)
            try:
                comment.reply("Thank you for your thoughtful comment! It counts towards your eligibility to post.")
                time.sleep(3)  # Increase delay between actions to handle rate limits
            except praw.exceptions.APIException as e:
                logging.error(f"Failed to reply to comment: {e}", exc_info=True)
        else:
            logging.debug("Comment does not meet the word count requirement.")
            try:
                comment.reply("Your comment is appreciated, but it needs to be at least 150 words to count towards your posting eligibility. Keep engaging!")
                time.sleep(3)  # Increase delay between actions to handle rate limits
            except praw.exceptions.APIException as e:
                logging.error(f"Failed to reply to comment: {e}", exc_info=True)
    return len(valid_comments) >= MIN_REPLIES

def reset_user_activity(username):
    logging.debug(f"Resetting activity for user: {username}")
    update_user_activity(username, 0, datetime.now().strftime('%Y-%m-%d'))

def monitor_subreddit():
    logging.info(f"Monitoring subreddit: {subreddit_name}")
    try:
        for submission in subreddit.stream.submissions(skip_existing=True):
            logging.info(f"New submission by {submission.author}: {submission.title}")
            author = submission.author
            if author:
                if check_user_eligibility(author):
                    logging.info(f"{author.name} is eligible to post.")
                    reset_user_activity(author)
                else:
                    logging.info(f"{author.name} is not eligible to post.")
                    try:
                        submission.mod.remove()
                        logging.info(f"Post by {author.name} removed.")
                        submission.reply(f"Hi {author.name}, your post has been removed because you have not met the required engagement criteria. Please engage with other members' music by making meaningful comments (at least 150 words each) and then try posting again. Thank you for understanding!")
                        time.sleep(3)  # Increase delay between actions to handle rate limits
                    except Exception as e:
                        logging.error(f"Failed to remove post by {author.name}: {e}", exc_info=True)
    except praw.exceptions.APIException as e:
        if e.error_type == 'RATELIMIT':
            logging.error(f"Rate limit exceeded: {e.message}. Waiting for 10 minutes.")
            time.sleep(600)  # Wait for 10 minutes before continuing
        else:
            logging.error(f"An error occurred: {e}", exc_info=True)

# Initialize the flat file
initialize_file()

if __name__ == "__main__":
    monitor_subreddit()
