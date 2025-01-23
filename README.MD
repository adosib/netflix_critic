# Netflix Critic 🕵️

## Demo
<p align="center">
<img src="./assets/critic-demo.gif" />
</p>

## Motivation
I sometimes spend up to half an hour looking for something to watch on Netflix. Finding something that's guaranteed to not be a waste of time is a huge challenge, and going in blind is a risk I'm not usually willing to take.

### Ratings
Ratings are usually a pretty good signal of quality — you can be reasonably certain you'll enjoy a show or movie that's been rated 9/10 by other viewers, unless you have some really niche taste or you're one of those contrarians types.

But why specifically the 'Google users' rating? Simply put, I've found it to be more reliable than any other ratings vendor. In my experience, Rotten Tomatoes and IMDb are often way off the mark. 

That's why I've put in the extra effort to collect that coveted percentage you see when you google a title:

<p align="center">
<img src="./assets/interstellar.png" />
</p>

## Running Locally
The extension isn't stand-alone because it depends on the web server (and the Postgres database) to pull data from, so at a minimum you'll need to have [Docker](https://www.docker.com/get-started/) installed.

Once you have Docker installed, open a terminal from the project root directory and run 
`docker compose up` after which your local webserver and database will be up and running.

Next you just have to add the extension:
1. Open a browser and go to chrome://extensions/
2. Toggle 'Developer mode'
3. Load unpacked extension
4. Select the extension-core directory

At this point you should be set. Now you can browse Netflix, enhanced with ratings.

<p align="center">
<img src="./assets/install-extension.gif" />
</p>

### Collecting Ratings Data
Optional: If you additionally want to actively pull down ratings data for titles that aren't readily available in the database, you should be able to get a free trial with some credits for the [Bright Data SERP API](https://brightdata.com/products/serp-api).

Beyond the free trial credits, it's pay-as-you-go at a rate of $1.50/1000 requests (as of the time of writing), which is very reasonably priced.

Once you've signed up all you need to do is create a .env file at the project root with an environment variable that holds your Bearer authentication token:

```
BRD_AUTH_TOKEN=...
```
*<path/to/netlfix_critic/.env*

## Learnings
[TODO]

## Loose Ends
[TODO]
- I'd love to include a Reddit sentiment score as part of this. I find Reddit threads to be even more reliable than Google user reviews.
- Testing is non-existent.
- Error handling could use some improvement.
- The data in the titles table needs to be cleaned up. There's a lot of "titles" in there that actually correspond to seasons and episodes. It poisons the data model (mixed entities).
- The `Availability` model (table) has a `country` attribute but right now all connections are just assumed to be US... the country code could be intercepted from e.g. `netflix.reactContext.models.geo.data.requestCountry` and sent as a query parameter when POSTing to /api/titles in the background script.
- 