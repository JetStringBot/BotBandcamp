import praw
import configparser
import csv
import os
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

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
subreddit_name = 'BandCamp'
subreddit = reddit.subreddit(subreddit_name)

# Path to the flat file in the same directory
file_path = 'user_activity.csv'

# Minimum word count and reply threshold
MIN_WORD_COUNT = 150
MIN_REPLIES = 5

def initialize_file():
    if not os.path.exists(file_path):
        with open(file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['username', 'comment_count', 'last_post_date'])

def read_user_activity():
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
    return list(user.comments.new(limit=limit))

def check_user_eligibility(user):
    comments = get_user_comments(user)
    valid_comments = []
    for comment in comments:
        if count_words(comment.body) >= MIN_WORD_COUNT:
            valid_comments.append(comment)
            comment.reply("Thank you for your thoughtful comment! It counts towards your eligibility to post.").mod.distinguish(how='yes')
        else:
            comment.reply("Your comment is appreciated, but it needs to be at least 150 words to count towards your posting eligibility. Keep engaging!").mod.distinguish(how='yes')
    return len(valid_comments) >= MIN_REPLIES

def reset_user_activity(username):
    update_user_activity(username, 0, datetime.now().strftime('%Y-%m-%d'))

def monitor_subreddit():
    logging.info("Starting to monitor subreddit...")
    for submission in subreddit.stream.submissions(skip_existing=True):
        logging.info(f"New submission by {submission.author}: {submission.title}")
        author = submission.author
        if author:
            if check_user_eligibility(author):
                logging.info(f"{author.name} is eligible to post.")
                reset_user_activity(author)
            else:
                logging.info(f"{author.name} is not eligible to post.")
                # Remove the post and leave a mod comment
                submission.mod.remove()
                submission.reply(f"Hi {author.name}, your post has been removed because you have not met the required engagement criteria. Please engage with other members' music by making meaningful comments (at least 150 words each) and then try posting again. Thank you for understanding!").mod.distinguish(how='yes', sticky=True)

# Initialize the flat file
initialize_file()

if __name__ == "__main__":
    monitor_subreddit()
