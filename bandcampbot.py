import praw
import configparser
import csv
import os
from datetime import datetime
import logging
import time
import praw
import configparser
import csv
import os
from datetime import datetime, timedelta
import logging
import time
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Construct the absolute path to the config.ini file
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, 'config.ini')

# Read the configuration file with interpolation disabled
config = configparser.ConfigParser(interpolation=None)
config.read(config_path)

# Set up your Reddit client using the config file
try:
    reddit = praw.Reddit(
        client_id=config['reddit']['client_id'],
        client_secret=config['reddit']['client_secret'],
        user_agent=config['reddit']['user_agent'],
        username=config['reddit']['username'],
        password=config['reddit']['password']
    )
    logging.info("Reddit client initialized successfully.")
except Exception as e:
    logging.error("Failed to initialize Reddit client.", exc_info=True)
    raise

# Define the subreddit to monitor
subreddit_name = 'TestBandcampBot'
try:
    subreddit = reddit.subreddit(subreddit_name)
    logging.info(f"Monitoring subreddit: {subreddit.display_name}")
except Exception as e:
    logging.error("Failed to connect to the subreddit.", exc_info=True)
    raise

# Path to the flat file in the same directory
file_path = 'user_activity.csv'

# Settings
MIN_WORD_COUNT_COMMENT = 70
MIN_WORD_COUNT_POST = 150
MIN_REPLIES = 5
MIN_KARMA = 15
COOLDOWN_DAYS = 14

# Track evaluated comments to prevent multiple evaluations per post
evaluated_comments = {}

# Disclaimer to be added to all bot messages
DISCLAIMER = "\n\n*This action has been performed by a bot. BandCamp_CPO V1.2 beta.*"

def initialize_file():
    try:
        if not os.path.exists(file_path):
            logging.debug("Initializing the file...")
            with open(file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['username', 'comment_count', 'last_post_date'])
    except Exception as e:
        logging.error("Failed to initialize the activity file.", exc_info=True)
        raise

def read_user_activity():
    try:
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
    except Exception as e:
        logging.error("Failed to read user activity file.", exc_info=True)
        return {}

def update_user_activity(username, comment_count, last_post_date):
    try:
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
    except Exception as e:
        logging.error("Failed to update user activity file.", exc_info=True)

def count_words(text):
    return len(text.split())

def get_user_comments(user, limit=100):
    try:
        logging.debug(f"Fetching comments for user: {user.name} from subreddit: {subreddit.display_name}")
        comments = list(user.comments.new(limit=limit))
        subreddit_comments = [
            comment for comment in comments
            if comment.subreddit.display_name == subreddit_name and not comment.removed
        ]
        return subreddit_comments
    except Exception as e:
        logging.error(f"Failed to fetch comments for user {user.name}.", exc_info=True)
        return []

def check_user_eligibility(user):
    try:
        logging.debug(f"Checking eligibility for user: {user.name}")
        # Skip evaluation if user is a moderator
        if user.name in [mod.name for mod in subreddit.moderator()]:
            logging.info(f"User {user.name} is a moderator and will not be evaluated.")
            return True
        
        # Check for minimum community karma
        if user.link_karma + user.comment_karma < MIN_KARMA:
            logging.info(f"User {user.name} does not meet the minimum community karma requirement.")
            return False

        comments = get_user_comments(user)
        valid_comments = []
        for comment in comments:
            # Ignore comments on posts without a Bandcamp link
            if not re.search(r"https?://\S+\.bandcamp\.com", comment.submission.selftext):
                continue
            
            # Only evaluate the first comment per post by checking if already processed
            if (user.name, comment.submission.id) in evaluated_comments:
                continue
            
            # Skip comments that have been removed by moderators
            if comment.banned_by:
                logging.debug(f"Comment by {user.name} on post {comment.submission.id} is removed and will be ignored.")
                continue

            if count_words(comment.body) >= MIN_WORD_COUNT_COMMENT:
                logging.debug("Comment is valid and counts towards eligibility.")
                valid_comments.append(comment)
                # Mark this comment as evaluated for this post
                evaluated_comments[(user.name, comment.submission.id)] = True
            else:
                logging.debug("Comment does not meet the word count requirement.")
        
        return len(valid_comments) >= MIN_REPLIES
    except Exception as e:
        logging.error(f"Error occurred while checking eligibility for user {user.name}.", exc_info=True)
        return False

def reset_user_activity(username):
    try:
        logging.debug(f"Resetting activity for user: {username}")
        update_user_activity(username, 0, datetime.now().strftime('%Y-%m-%d'))
    except Exception as e:
        logging.error(f"Failed to reset activity for user {username}.", exc_info=True)

def monitor_subreddit():
    try:
        for submission in subreddit.stream.submissions(skip_existing=True):
            try:
                logging.info(f"New submission by {submission.author}: {submission.title}")
                logging.debug(f"Submission title: {submission.title}")
                logging.debug(f"Submission selftext: {submission.selftext}")
                author = submission.author
                
                # Define the Bandcamp link pattern
                bandcamp_pattern = r"https?://\S+\.bandcamp\.com"
                
                # Check if the post contains a Bandcamp link
                if re.search(bandcamp_pattern, submission.selftext) or re.search(bandcamp_pattern, submission.title):
                    logging.info(f"Detected a Bandcamp link in post by {author.name}.")
                    word_count = count_words(submission.selftext)
                    user_activity = read_user_activity()
                    last_post_date = user_activity.get(author.name, {}).get('last_post_date')
                    
                    # Check cooldown
                    if last_post_date:
                        last_post_date = datetime.strptime(last_post_date, '%Y-%m-%d')
                        if datetime.now() - last_post_date < timedelta(days=COOLDOWN_DAYS):
                            logging.info(f"User {author.name} is in cooldown period. Post removed.")
                            submission.mod.remove()
                            submission.reply(
                                f"Hi {author.name}, you can only post once every {COOLDOWN_DAYS} days with a Bandcamp link. Please wait until the cooldown period ends."
                                + DISCLAIMER
                            )
                            continue
                    
                    if word_count >= MIN_WORD_COUNT_POST:
                        if author and check_user_eligibility(author):
                            logging.info(f"{author.name} is eligible to post.")
                            reset_user_activity(author)
                        else:
                            logging.info(f"{author.name} is not eligible to post.")
                            submission.mod.remove()
                            submission.reply(
                                f"Hi {author.name}, your post has been removed because you haven't met the engagement criteria (5 comments, 70 words each, 15 community karma)."
                                + DISCLAIMER
                            )
                    else:
                        logging.info(f"Post by {author.name} removed due to insufficient description word count.")
                        submission.mod.remove()
                        submission.reply(
                            f"Hi {author.name}, your post has been removed because it does not meet the 150-word description requirement. "
                            "Please include a meaningful description of your music and creative process. Thank you!"
                            + DISCLAIMER
                        )
                else:
                    logging.info(f"No Bandcamp link detected in {author.name}'s post. No action needed.")
            except Exception as e:
                logging.error(f"Error processing submission {submission.id}.", exc_info=True)
    except Exception as e:
        logging.error("Critical error in the monitor loop.", exc_info=True)

# Initialize the flat file
try:
    initialize_file()
except Exception as e:
    logging.error("Critical error during file initialization.", exc_info=True)
    raise

if __name__ == "__main__":
    try:
        monitor_subreddit()
    except Exception as e:
        logging.error("Critical error in the main loop.", exc_info=True)

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
    # Skip evaluation if user is a moderator
    if user.name in [mod.name for mod in subreddit.moderator()]:
        logging.info(f"User {user.name} is a moderator and will not be evaluated.")
        return True
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
