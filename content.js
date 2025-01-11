
(async function() {
    console.log("Chrome extension 'Netflix Critic' activated");
    
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = chrome.runtime.getURL('styles.css');
    document.head.appendChild(link);
    
    // TODO probably move all this stuff to the background
    try {
        // Await the fetch operation and handle errors
        const data = await getData("http://localhost:8000/api/titles");
        
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
            return this.#rating;
        }
        const rating = this.getProperty("rating");
        this.#rating = rating;  // Cache the result
        return rating;
    }

    async #lookup(){
        const cachedData = await chrome.storage.local.get(this.netflixId.toString());
        if (Object.keys(cachedData).length > 0){
            return cachedData[this.netflixId];
        }
        chrome.runtime.sendMessage({
            type: 'missingTitleData',
            netflixId: this.netflixId
        });
        return null;
    }

}

async function reloadDOM(){
    let lolomoRows = document.querySelectorAll(
        '.lolomoRow'+
        // Exclude live/upcoming
        ':not([data-list-context="configbased_liveandupcomingepisodes"])'+
        // Exclude mobile games
        ':not([data-list-context="configbased_mobilepersonalizedgames"])'
    );

    for (const lolomoRow of lolomoRows){

        let titleCardsArr = lolomoRow.querySelectorAll(
            '.title-card-container'+
            ':not([data-netflix-critic-processed="true"])'
        );

        for(const titleCard of titleCardsArr){
            let title = new TitleCard(titleCard);
            // TODO handle all processing in the constructor
            title.divElement.innerHTML += "<div class=netflix-critic><p>" + await title.googleRating + "</p></div>";
        }
    }
}