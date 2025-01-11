let payload = new Set();
let sendTimeout = null;

chrome.commands.onCommand.addListener((shortcut) => { // TODO remove
    if(shortcut.includes("+M")) {
        chrome.tabs.reload();
        chrome.runtime.reload();
    }
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'missingTitleData') {
        // Add data to the payload
        payload.add(message.netflixId);

        // Clear the existing timeout if any
        if (sendTimeout) {
            clearTimeout(sendTimeout);
        }

        // Set a new timeout to send the payload after 1 second
        sendTimeout = setTimeout(() => {
            sendPayload();
        }, 1000);
    }
});

function sendPayload() {
    if (payload.size === 0) return;

    const dataToSend = Array.from(payload); // Copy the current payload
    payload = new Set(); // Clear the payload

    fetch('http://localhost:8000/api/titles', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(dataToSend),
    })
        .then(response => response.json())
        .then(data => {
            console.log('Payload sent successfully:', data);
            chrome.storage.local.set(data);
        })
        .catch(error => {
            console.error('Error sending payload:', error);
        });
}
