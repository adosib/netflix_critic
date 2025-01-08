
(async function() {
    console.log("Chrome extension 'Netflix Critic' activated");

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = chrome.runtime.getURL('styles.css');
    document.head.appendChild(link);

    try {
        // Await the fetch operation and handle errors
        const data = await getData("http://localhost:8000/api/titles");

        // Check if data exists before proceeding
        if (data) {
            for (const key in data) {
                localStorage.setItem(key, JSON.stringify(data[key]));
            }
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

    constructor(divElement){
        // Check if the passed element is a valid DOM node and has the expected structure
        if (!(divElement instanceof HTMLDivElement)){
            throw new Error("Expected an HTMLDivElement.");
        }
        this.divElement = divElement;
        divElement.dataset.netflixCriticProcessed = true;
        divElement.netflixCriticTitleCardObj = this;
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
        return this.getProperty("content_type");
    }
    
    get releaseYear() {
        return this.getProperty("release_year");
    }
    
    get runtime() {
        return this.getProperty("runtime");
    }

    #storeData(jsonData){
        localStorage.setItem(jsonData["netflix_id"], JSON.stringify(jsonData));
    }

    async #lookup(){
        const cachedData = localStorage.getItem(this.netflixId);
        if(cachedData){
            return JSON.parse(cachedData);
        }
        // Right now, if the title isn't found, this can get called over and over. I need to fix that.
        const jsonData = await getData(`http://localhost:8000/api/title/${this.netflixId}`); // TODO set off some async function here
        if(jsonData){
            this.#storeData(jsonData);
            return jsonData;
        }
        return null;
    }

}

function reloadDOM(){
    // TODO I probably want to narrow this selector down to elements I haven't processed already, if possible
    let titleCardsArr = document.querySelectorAll('.title-card-container:not([data-netflix-critic-processed="true"])');
    for(i = 0; i < titleCardsArr.length; i++){
        let title = new TitleCard(titleCardsArr[i])
        // TODO handle all processing in the constructor
        title.divElement.innerHTML += "<div class=netflix-critic><p>" + title.runtime + "</p></div>";
    }
}

function callbackFunc(backgroundMessage){
    // Send movie titles without ratings to the background script
    chrome.runtime.sendMessage(backgroundMessage);
}