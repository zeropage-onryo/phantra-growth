Hand-written listings in the shape PRAW's `subreddit(name).new()` yields:
one object per Submission with the attributes the facade reads (`id`,
`title`, `selftext`, `author.name`, `permalink`, `url`, `created_utc`,
`score`, `num_comments`, `is_self`, `link_flair_text`, `over_18`). Not
recorded from Reddit; invented so the tests own them.
