const BASE_URL = "http://localhost:80";
(async function() {
    console.log("Chrome extension 'Netflix Critic' activated");

    // chrome.storage.local.clear(); // TODO remove
    
    // TODO probably move all this stuff to the background
    try {
        // Await the fetch operation and handle errors
        const data = await getData(`${BASE_URL}/api/titles`);
        
        // Check if data exists before proceeding
        if (data) {
            chrome.storage.local.set(data);
        } else {
            console.error("No data returned from the API.");
        }
    } catch (error) {
        console.error("Error fetching data:", error);
    }
    
})();


let scrollTimer = -1; // init
function bodyScroll(){
    if(scrollTimer != -1){
        window.clearTimeout(scrollTimer); // https://developer.mozilla.org/en-US/docs/Web/API/Window/clearTimeout
    }
    // run function reloadDOM after 500 ms
    scrollTimer = window.setTimeout(reloadDOM, 500);
}

function click(){
    setTimeout(reloadDOM, 1000);
}

document.addEventListener("wheel", bodyScroll);
document.addEventListener("mousedown", click);

async function getData(url){
    try {
      const response = await fetch(url);
      if (!response.ok){
        throw new Error(`Response status: ${response.status}`);
      }
  
      const json = await response.json();
      return json;
    } catch (error){
      console.error(error.message);
      return null;
    }
}

class TitleCard {
    // Private cache
    #netflixId = null;
    #contentType = null;
    #releaseYear = null;
    #runtime = null;
    #rating = null;

    constructor(divElement){
        // Check if the passed element is a valid DOM node and has the expected structure
        if (!(divElement instanceof HTMLDivElement)){
            throw new Error("Expected an HTMLDivElement.");
        }
        this.divElement = divElement;
        divElement.dataset.netflixCriticProcessed = true;
    }

    get netflixId() {
        if (this.#netflixId) {
            return this.#netflixId;
        }

        const watchLink = this.divElement.querySelector('a').href;
        const splitPath = URL.parse(watchLink).pathname.split('/');
        const parsedId = parseInt(splitPath[splitPath.length - 1]);

        this.#netflixId = parsedId;  // Cache the result

        return parsedId;
    }

    get title(){
        return this.divElement.getElementsByClassName("fallback-text")[0].innerText;
    }

    async getProperty(property) {
        const data = await this.#lookup();
        try {
            return data[property];
        } catch (TypeError) {
            return null;
        }
    }

    get contentType() {
        if (this.#contentType) {
            return this.#contentType;
        }
        const contentType = this.getProperty("content_type");
        this.#contentType = contentType;  // Cache the result
        return contentType;
    }
    
    get releaseYear() {
        if (this.#releaseYear) {
            return this.#releaseYear;
        }
        const releaseYear = this.getProperty("release_year");
        this.#releaseYear = releaseYear;  // Cache the result
        return releaseYear;
    }
    
    get runtime() {
        if (this.#runtime) {
            return this.#runtime;
        }
        const runtime = this.getProperty("runtime");
        this.#runtime = runtime;  // Cache the result
        return runtime;
    }

    get googleRating() {
        if (this.#rating) {
            return Promise.resolve(this.#rating);
        }
        return this.getProperty("google_users_rating").then((rating) => {
            this.#rating = rating; // Cache the rating
            return rating;
        });
    }

    async #lookup() {
        const key = this.netflixId.toString();
        const timeout = 120 * 1000;
        const interval = 0.5 * 1000;
    
        // Helper function: Check chrome.storage for the cached data
        const getCachedData = async () => {
            const cachedData = await chrome.storage.local.get(key);
            return Object.keys(cachedData).length > 0 ? cachedData[key] : null;
        };
    
        // Helper function: Set up polling with timeout
        const pollForData = (resolve, reject) => {
            let elapsed = 0;
    
            const intervalId = setInterval(async () => {
                elapsed += interval;
    
                const data = await getCachedData();
                if (data) {
                    clearInterval(intervalId);
                    resolve(data);
                    return;
                }
    
                if (elapsed >= timeout) {
                    clearInterval(intervalId);
                    resolve(null);
                }

            }, interval);
        };
    
        // Main execution
        const cachedData = await getCachedData();
        if (cachedData) return cachedData; // Return immediately if data exists
    
        // Notify background script to fetch the data
        chrome.runtime.sendMessage({
            type: 'missingTitleData',
            netflixId: this.netflixId
        });
    
        // Poll for data and handle timeout
        return new Promise(pollForData);
    }
    

}

function getColorForValue(value) {
    // Ensure value is within 0-100 range
    value = Math.min(100, Math.max(0, value));

    if (value <= 50) {
        // Transition from red to yellow (0-50)
        const ratio = value / 50;
        const r = Math.round(220 + ratio * (240 - 220)); // Red fades
        const g = Math.round(80 + ratio * (200 - 80));  // Green increases
        const b = Math.round(80);                      // Blue remains constant
        return `rgb(${r}, ${g}, ${b})`;
    } else {
        // Transition from yellow to green (51-100)
        const ratio = (value - 50) / 50;
        const r = Math.round(240 - ratio * (240 - 100)); // Red decreases
        const g = Math.round(200 + ratio * (180 - 200)); // Green increases
        const b = Math.round(80 + ratio * (100 - 80));   // Blue increases slightly
        return `rgb(${r}, ${g}, ${b})`;
    }
}


async function reloadDOM(){
    const exclusions = (
        // Exclude live/upcoming
        ':not([data-list-context="configbased_liveandupcomingepisodes"])'+
        // Exclude mobile games
        ':not([data-list-context="configbased_mobilepersonalizedgames"])'+
        ':not([data-list-context="configbased_cloudpersonalizedgames"])'
    );
    const titleCardQuery = (
        '.title-card-container'+
        ':not([data-netflix-critic-processed="true"])'
    );

    let lolomoRows = document.querySelectorAll(
        '.lolomoRow' + exclusions + ', ' +
        '.rowContainer' + exclusions
    );
    let titleCardsArr = [];

    for (const lolomoRow of lolomoRows){
        titleCardsArr.push(...lolomoRow.querySelectorAll(titleCardQuery));
    }
    if(lolomoRows.length === 0){
        // This is a fall-back because I want the exclusions, otherwise I would just
        // call this and be done with it
        titleCardsArr.push(...document.querySelectorAll(titleCardQuery));
    }
    
    for(const titleCard of titleCardsArr){
        let title = new TitleCard(titleCard);
        
        const ratingDiv = document.createElement('div');
        ratingDiv.className = "netflix-critic";
        
        const ratingSpinnerDiv = document.createElement('div');
        ratingSpinnerDiv.className = 'spinner';

        ratingDiv.appendChild(ratingSpinnerDiv)
        title.divElement.appendChild(ratingDiv);

        title.googleRating.then((rating) => {
            ratingSpinnerDiv.remove();
            ratingDiv.style.color = getColorForValue(rating);
            ratingDiv.innerHTML = `<p>${rating || "N/A"}</p>`;
        });
        
    }
}