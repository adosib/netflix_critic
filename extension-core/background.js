let payload = new Set();
let sendTimeout = null;
const eventSources = new Map(); // To track active EventSource instances
const BASE_URL = "http://localhost:80";

chrome.commands.onCommand.addListener((shortcut) => { // TODO remove
    if(shortcut.includes("+M")) {
        chrome.tabs.reload();
        chrome.runtime.reload();
    }
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    
    if (message.type === 'missingTitleData') {
        payload.add(message.netflixId);

        if (sendTimeout) {
            clearTimeout(sendTimeout);
        }

        sendTimeout = setTimeout(() => {
            sendPayload();
        }, 1000);
    }
    else if (message.type === 'activated') {
        chrome.scripting.executeScript({
            target : {tabId : sender.tab.id},
            func: () => {
                let country = 'US';
                try {
                    country = netflix.reactContext.models.geo.data.requestCountry.id;
                } catch (error) {
                    console.error(error);
                }
                return country;
            },
            // https://developer.chrome.com/docs/extensions/reference/api/scripting#type-ExecutionWorld
            world: "MAIN"
        }).then(injectionResults => {
            for (const {frameId, result} of injectionResults) {
              chrome.storage.local.set({"COUNTRY": result});
            }
        });
    }
});

function sendPayload() {
    if (payload.size === 0) return;

    const dataToSend = Array.from(payload);
    payload = new Set();

    chrome.storage.local.get({"COUNTRY": "US"}).then((country) => {
        return fetch(`${BASE_URL}/api/titles?` + new URLSearchParams({country: country["COUNTRY"]}).toString(), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(dataToSend),
        })
    })
    .then((response) => {
        if (!response.ok) {
            throw new Error(`Failed to send payload: ${response.statusText}`);
        }
        return response.json();
    })
    .then((data) => {

        console.log('Payload sent successfully:', dataToSend);

        const jobId = data.job_id;
        const eventSource = new EventSource(
            `${BASE_URL}/api/stream/${jobId}`
        );

        eventSource.onmessage = (event) => {
            try {
                const parsedData = JSON.parse(event.data);
                console.log(`Received data for jobId ${jobId}:`, parsedData);
                chrome.storage.local.set(parsedData);
            } catch (error) {
                console.error('Error parsing incoming data:', error);
            }
        };

        eventSource.onerror = (err) => {
            console.error(`SSE connection error for job_id ${jobId}:`, err);
            eventSource.close();
            eventSources.delete(jobId);
        };

        eventSources.set(jobId, eventSource);

    })
    .catch((error) => {
        console.error('Error sending payload:', error);
    });
}