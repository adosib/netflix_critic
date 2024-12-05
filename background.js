console.log("background running");

chrome.runtime.onMessage.addListener(receiver);

// TODO: Find a way of securely storing the API key
var api_key = ""
// example request: https://api.themoviedb.org/3/movie/550?api_key=aeb21d85f352c4c50978e7ff8fe8177b

function receiver(request, sender, sendResponse){
    console.log(request);
    // If the slug has the genre/83 or genre/[0-9]+?bc=83, it's a TV show
    // If slug has genre/34399 or genre/[0-9]+?bc=34399, it's a movie
    if(request[0])
    let movie = Object.keys(request)[0];  // The first movie in the object
    movie = '"' + movie + '"';  // phrase match
    // Build the API request URL
    let search = 'https://api.themoviedb.org/3/search/movie?api_key=' + 
                 api_key + 
                 '&query=' + movie;
    // Make the request to the API endpoint and handle it
    let rating = $.getJSON(search);
    console.log(rating);

}