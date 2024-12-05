// This function is executed in the context of every page loaded by the APIfy web-scraper Actor.
// For a complete list of its properties and functions,
// see https://apify.com/apify/web-scraper#page-function 
async function pageFunction(context) {
    const html = new XMLSerializer().serializeToString(document);
    const googleUserRating = document.querySelector('[data-attrid$="thumbs_up"]');
    let allRatings = [...document.querySelectorAll('[data-attrid$="reviews"]')];
    
    // Print some information to actor log
    context.log.info(`URL: ${context.request.url}`);
    
    // If the google user rating isn't present, we're going to try alternative search paths
    const searchPaths = context.customData["alt_search_paths"];
    if(!googleUserRating){
        for (const url of searchPaths) {
            await context.enqueueRequest({ url });
        }
    }
    else{
        allRatings.push(googleUserRating);
    }

    // Return an object with the data extracted from the page.
    // It will be stored to the resulting dataset.
    context.log.info(context.request)
    return {
        url: context.request.url,
        loadedUrl: context.request.loadedUrl,
        handledAt: context.request.handledAt,
        headers: context.request.headers,
        allRatings,
        html
    };
}