
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

async function extractContextVarFromTitlePage(netflixId) {

    const url = `https://www.netflix.com/title/${netflixId}`;
    const response = await fetch(url, {method: 'GET', credentials: 'omit',});
    if (!response.ok) {
      throw new Error(`Request for ${url} failed with status ${response.status}`);
    }
    const html = await response.text();

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    
    const scriptTags = doc.querySelectorAll('script');
    let scriptContent = null;
  
    scriptTags.forEach(script => {
      if (script.textContent.includes('netflix.reactContext')) {
        scriptContent = script.textContent.replaceAll('netflix.reactContext', `netflix.reactContext${netflixId}`);
      }
    });
  
    if (!scriptContent) {
      throw new Error(`Could not find script with netflix.reactContext for title with ID ${netflixId}`);
    }
  
    const scriptId = `netflix-critic-script-${netflixId}`;
    // Create a temporary script element to evaluate the script content
    if(!document.scripts.namedItem(scriptId)){
        const script = document.createElement('script');
        script.classList.add('netflix-critic');
        script.id = scriptId;
        script.textContent = scriptContent;
        document.body.appendChild(script);
    }

    const contextVar = window.netflix[`reactContext${netflixId}`];
    console.log(contextVar);

    setTimeout(() => {
        document.body.removeChild(document.scripts.namedItem(scriptId));
    }, 2000);
    
    return contextVar.models.nmTitleUI.data.sectionData;
}

class TitleCard {
    constructor(divElement){
        // Check if the passed element is a valid DOM node and has the expected structure
        if (!(divElement instanceof HTMLDivElement)){
            throw new Error("Expected an HTMLDivElement.");
        }
        this.divElement = divElement;
        this.data = this.fetchData();
        divElement.dataset.netflixCriticProcessed = true;
        divElement.netflixCriticTitleCardObj = this;
    }

    // Private cache
    #netflixId = null;

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

    async fetchData(){
        const data = await extractContextVarFromTitlePage(this.netflixId);
        return data;
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
        //return this.getProperty("runtime");
        const runtimeSeconds = this.data.then((data) => { data[0].data.details[0].data.runtime; });
        // const runtimeSeconds = data[0].data.details[0].data.runtime;
        // return new Date(runtimeSeconds * 1000).toISOString().substring(11, 16);
        return runtimeSeconds;
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
    let titleCardsSet = new Set();  // to hold unique movie titles
    let titleCardsDict = {};  // to hold movie-rating pairs
    let backgroundMessage = ["url", {}]; // will store 2 elements, the URL and the movies dict

    // TODO I probably want to narrow this selector down to elements I haven't processed already, if possible
    let titleCardsArr = document.querySelectorAll('.title-card-container:not([data-netflix-critic-processed="true"])');
    for(i = 0; i < titleCardsArr.length; i++){
        let title = new TitleCard(titleCardsArr[i])
        // TODO handle all processing in the constructor
        title.divElement.innerHTML += "<div class=netflix-critic><p>" + title.runtime + "</p></div>";
    }
    // TODO vvv clean up this crap
    // backgroundMessage[0] = window.location.toString();
    // backgroundMessage[1] = titleCardsDict;
    // console.log(titleCardsSet);
    // console.log(titleCardsSet.size);
    // console.log(backgroundMessage);
    // callbackFunc(backgroundMessage);
}

function getRating(){
    let rating = "NA";
    return rating;
}

function callbackFunc(backgroundMessage){
    // Send movie titles without ratings to the background script
    chrome.runtime.sendMessage(backgroundMessage);
}