// script.js
ort.env.wasm.numThreads = navigator.hardwareConcurrency || 32;
ort.env.wasm.simd = true;

// Get references to HTML elements
const statusText = document.getElementById('status');
const outputCanvas = document.getElementById('outputCanvas');
const outputCtx = outputCanvas.getContext('2d');
const video = document.getElementById('webcam');

let _keypointSession, _generatorSession, _kpSource;

const sessionManager = {
    get keypointSession() {
        return _keypointSession;
    },
    set keypointSession(value) {
        _keypointSession = value;
    },
    get generatorSession() {
        return _generatorSession;
    },
    set generatorSession(value) {
        _generatorSession = value;
    },
    get kpSource() {
        return _kpSource;
    },
    set kpSource(value) {
        _kpSource = value;
    }
};

// Optionally, you can expose these directly if not needed to be private
let { keypointSession, generatorSession } = sessionManager;

(async () => {
    try {
        // Update status
        statusText.textContent = 'Loading source image...';

        // Load the source image
        //const sourceImage = await loadImage('/vcaa/avatar1f.png'); // Ensure the image is in the same directory
        const sourceImage = await loadImage('/vcaa/source3.jpg'); // Ensure the image is in the same directory
        console.log('Source image loaded.');
        statusText.textContent = 'Source image loaded.';

        // Preprocess the source image
        const sourceTensor = preprocessImage(sourceImage);
        console.log('Source image preprocessed into tensor.');

        // Load the ONNX models with WebGPU backend, with fallback to optimized WASM
        statusText.textContent = 'Loading ONNX models...';
        console.log('Loading ONNX models...');

        let usingGPU = false;

        try {
            // Try to create sessions with WebGPU backend
            const sessionOptions = { executionProviders: ['webgpu'],preferredOutputLocation:'gpu-buffer' };
            sessionManager.keypointSession = await ort.InferenceSession.create('/vcaa/kp_detector.onnx', sessionOptions);
            sessionManager.generatorSession = await ort.InferenceSession.create('/vcaa/generator.onnx', sessionOptions);

            // Log execution providers
            console.log('Keypoint Session Execution Provider:', sessionManager.keypointSession.executionPlan ? 'webgpu' : 'unknown');
            console.log('Generator Session Execution Provider:', sessionManager.generatorSession.executionPlan ? 'webgpu' : 'unknown');

            statusText.textContent = 'Models loaded successfully with WebGPU backend!';
            console.log('Models loaded successfully with WebGPU backend!');
            usingGPU = true;
        } catch (error) {
            console.error('Failed to initialize WebGPU backend. Falling back to optimized WASM backend.', error);

            // Fallback to optimized WASM backend
            ort.env.wasm.numThreads = navigator.hardwareConcurrency || 32; // Use available CPU cores
            ort.env.wasm.simd = true; // Enable SIMD

            sessionManager.keypointSession = await ort.InferenceSession.create('/vcaa/kp_detector.onnx');
            sessionManager.generatorSession = await ort.InferenceSession.create('/vcaa/generator.onnx');

            // Log execution providers
            console.log('Keypoint Session Execution Provider:', 'wasm');
            console.log('Generator Session Execution Provider:', 'wasm');

            statusText.textContent = 'Models loaded with optimized WASM backend.';
            console.log('Models loaded with optimized WASM backend.');
            usingGPU = false;
        }

        // Log whether GPU is being used
        if (usingGPU) {
            console.log('Running inference on the GPU.');
            statusText.textContent += ' Running inference on the GPU.';
        } else {
            console.log('Running inference on the CPU (optimized WASM backend).');
            statusText.textContent += ' Running inference on the CPU (optimized WASM backend).';
        }

        console.log('Keypoint Detector input names:', sessionManager.keypointSession.inputNames);
        console.log('Keypoint Detector output names:', sessionManager.keypointSession.outputNames);
        console.log('Generator input names:', sessionManager.generatorSession.inputNames);
        console.log('Generator output names:', sessionManager.generatorSession.outputNames);

        // Run keypoint detector on the source image
        statusText.textContent = 'Running keypoint detector on source image...';
        sessionManager.kpSource = await runKeypointDetector(sessionManager.keypointSession, sourceTensor);
        console.log('Keypoints for source image obtained.');

        // Initialize webcam
        statusText.textContent = 'Initializing webcam...';
        await initializeWebcam(video);
        statusText.textContent = 'Webcam initialized. Starting live inference...';

        // Variables to store the initial keypoints from the driving video
        let kpDrivingInitial = null;

        // Start processing frames
        const processFrame = async () => {
            // Capture a frame from the webcam
            let kpDriving;
            ({ kpDriving, kpDrivingInitial } = await ConvertVideoToKeypoints(sessionManager.keypointSession, kpDrivingInitial));

            //await displayKeypoints(sessionManager.kpSource, kpDriving, kpDrivingInitial, sessionManager.generatorSession, sourceTensor);

            // Normalize keypoints
            const kpNormalized = normalizeKp(sessionManager.kpSource, kpDriving, kpDrivingInitial);

            decodeURI.send( )

            // Continue processing frames
            requestAnimationFrame(processFrame);
        };

        // Start processing frames
        // DISABLED processFrame();

    } catch (error) {
        statusText.textContent = 'Error occurred. Check console for details.';
        console.error('An error occurred:', error);
    }
})();

async function ConvertVideoToKeypoints(keypointSession, kpDrivingInitial) {
    const frameTensor = captureWebcamFrame(video);

    // Run keypoint detector on the driving image
    const kpDriving = await runKeypointDetector(keypointSession, frameTensor);

    // Initialize kpDrivingInitial if it's the first frame
    if (!kpDrivingInitial) {
        kpDrivingInitial = {
            value: kpDriving.value,
            jacobian: kpDriving.jacobian
        };
    }
    return { kpDriving, kpDrivingInitial };
}

async function displayKeypoints(kpSource, kpDriving, kpDrivingInitial, generatorSession, sourceTensor) {
    // Normalize keypoints
    const kpNormalized = normalizeKp(kpSource, kpDriving, kpDrivingInitial);

    // Prepare inputs for the generator model
    const generatorInputs = prepareGeneratorInputs(generatorSession, sourceTensor, kpSource, kpNormalized);

    // Run the generator model
    const generatedImageTensor = await runGenerator(generatorSession, generatorInputs);

    // Post-process and display the generated image
    displayGeneratedImage(generatedImageTensor, outputCtx);
}

// Function to load an image and return a Promise that resolves to the Image object
function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous'; // Handle CORS if necessary
        img.onload = () => resolve(img);
        img.onerror = (err) => reject(err);
        img.src = src;
    });
}

// Function to preprocess the image into a tensor
function preprocessImage(image) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    // Draw the image onto the canvas and get the pixel data
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    // Convert to Float32Array in CHW format
    const data = imageData.data; // Uint8ClampedArray
    const width = canvas.width;
    const height = canvas.height;
    const floatData = new Float32Array(1 * 3 * height * width);

    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const idx = y * width + x;
            const idx4 = idx * 4;
            const r = data[idx4] / 255.0;
            const g = data[idx4 + 1] / 255.0;
            const b = data[idx4 + 2] / 255.0;

            // Convert to CHW format
            floatData[0 * height * width + idx] = r;
            floatData[1 * height * width + idx] = g;
            floatData[2 * height * width + idx] = b;
        }
    }

    const inputTensor = new ort.Tensor('float32', floatData, [1, 3, height, width]);
    return inputTensor;
}

// Function to run the keypoint detector model
async function runKeypointDetector(session, inputTensor) {
    const feeds = {};
    const inputName = session.inputNames[0]; // Assuming the model has one input
    feeds[inputName] = inputTensor;

    const results = await session.run(feeds);

    // Extract outputs
    const kpValue = results[session.outputNames[0]];      // e.g., 'output' or 'kp_value'
    const kpJacobian = results[session.outputNames[1]];   // e.g., 'jacobian'

    return {
        value: kpValue,
        jacobian: kpJacobian
    };
}

// Function to initialize the webcam
async function initializeWebcam(videoElement) {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    videoElement.srcObject = stream;

    return new Promise((resolve) => {
        videoElement.onloadedmetadata = () => {
            videoElement.play();
            resolve();
        };
    });
}

// Function to capture a frame from the webcam and preprocess it
function captureWebcamFrame(videoElement) {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    // Convert to Float32Array in CHW format
    const data = imageData.data; // Uint8ClampedArray
    const width = canvas.width;
    const height = canvas.height;
    const floatData = new Float32Array(1 * 3 * height * width);

    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const idx = y * width + x;
            const idx4 = idx * 4;
            const r = data[idx4] / 255.0;
            const g = data[idx4 + 1] / 255.0;
            const b = data[idx4 + 2] / 255.0;

            // Convert to CHW format
            floatData[0 * height * width + idx] = r;
            floatData[1 * height * width + idx] = g;
            floatData[2 * height * width + idx] = b;
        }
    }

    const inputTensor = new ort.Tensor('float32', floatData, [1, 3, height, width]);
    return inputTensor;
}

// Function to prepare inputs for the generator model
function prepareGeneratorInputs(session, sourceTensor, kpSource, kpDriving) {
    const feeds = {};

    // Use the exact input names from the generator model
    const inputNames = session.inputNames;

    // Map the inputs correctly
    feeds[inputNames[0]] = sourceTensor;          // e.g., 'source'
    feeds[inputNames[1]] = kpSource.value;        // e.g., 'kp_source'
    feeds[inputNames[2]] = kpSource.jacobian;     // e.g., 'jacobian_source'
    feeds[inputNames[3]] = kpDriving.value;       // e.g., 'kp_driving'
    feeds[inputNames[4]] = kpDriving.jacobian;    // e.g., 'jacobian_driving'

    return feeds;
}

// Function to run the generator model
async function runGenerator(session, inputs) {
    // Run the generator model with the provided inputs
    const results = await session.run(inputs);

    // Assuming the output image is in the first output
    const generatedImageTensor = results[session.outputNames[0]];

    return generatedImageTensor;
}

// Function to display the generated image on the canvas
function displayGeneratedImage(tensor, ctx) {
    const data = tensor.data;
    const [batch, channels, height, width] = tensor.dims;

    // Create an ImageData object
    const imageData = ctx.createImageData(width, height);

    // Convert CHW tensor data to ImageData (RGBA)
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const idx = y * width + x;

            const r = data[0 * height * width + idx];
            const g = data[1 * height * width + idx];
            const b = data[2 * height * width + idx];

            const pixelIdx = idx * 4;
            imageData.data[pixelIdx] = Math.min(Math.max(r * 255, 0), 255);
            imageData.data[pixelIdx + 1] = Math.min(Math.max(g * 255, 0), 255);
            imageData.data[pixelIdx + 2] = Math.min(Math.max(b * 255, 0), 255);
            imageData.data[pixelIdx + 3] = 255; // Alpha channel
        }
    }

    // Draw the image on the canvas
    ctx.putImageData(imageData, 0, 0);
}

// Function to normalize keypoints
async function normalizeKp(kpSource, kpDriving, kpDrivingInitial) {
    // Compute movement scale
    // const adaptMovementScale = computeMovementScale(kpSource.value.data, kpDrivingInitial.value.data);

    // Normalize keypoint values
    const data = await kpDriving.value.getData();
    const numKeypoints = data.length;
    const kpValueNormalizedData = new Float32Array(numKeypoints);

    const dataSource = await kpSource.value.getData();

    for (let i = 0; i < numKeypoints; i++) {
        const diff = (data[i] - kpDrivingInitial.value.data[i]) * 1;
        kpValueNormalizedData[i] = diff + dataSource[i];
    }

    const kpValueNormalized = new ort.Tensor('float32', kpValueNormalizedData, kpDriving.value.dims);

    // Normalize jacobians
    const kpJacobianNormalizedData = normalizeJacobians(
        await kpSource.jacobian.getData(),
        await kpDriving.jacobian.getData(),
        await kpDrivingInitial.jacobian.getData()
    );

    const kpJacobianNormalized = new ort.Tensor('float32', kpJacobianNormalizedData, kpDriving.jacobian.dims);

    return {
        value: kpValueNormalized,
        jacobian: kpJacobianNormalized
    };
}

function computeMovementScale(kpSourceData, kpDrivingInitialData) {
    const sourceArea = computeConvexHullArea(kpSourceData);
    const drivingArea = computeConvexHullArea(kpDrivingInitialData);
    return Math.sqrt(sourceArea) / Math.sqrt(drivingArea);
}

function computeConvexHullArea(points) {
    // Convert flat array to array of points
    const pointArray = [];
    for (let i = 0; i < points.length; i += 2) {
        pointArray.push([points[i], points[i + 1]]);
    }

    // Use the convex-hull library
    const hullIndices = convexHull(pointArray);
    const hullPoints = hullIndices.map(index => pointArray[index]);

    // Compute area of the convex hull polygon
    const area = polygonArea(hullPoints);
    return area;
}

function polygonArea(points) {
    // Compute the area of a polygon given its vertices
    let area = 0;
    const numPoints = points.length;
    for (let i = 0; i < numPoints; i++) {
        const x1 = points[i][0];
        const y1 = points[i][1];
        const x2 = points[(i + 1) % numPoints][0];
        const y2 = points[(i + 1) % numPoints][1];
        area += (x1 * y2) - (x2 * y1);
    }
    return Math.abs(area) / 2;
}

function normalizeJacobians(kpSourceJacobianData, kpDrivingJacobianData, kpDrivingInitialJacobianData) {
    // kpJacobian data has shape [1, numKeypoints, 2, 2]
    const numKeypoints = kpSourceJacobianData.length / 4; // Each 2x2 matrix has 4 elements
    const kpJacobianNormalizedData = new Float32Array(kpSourceJacobianData.length);

    for (let i = 0; i < numKeypoints; i++) {
        const index = i * 4;

        // Extract 2x2 matrices
        const js = [
            [kpSourceJacobianData[index], kpSourceJacobianData[index + 1]],
            [kpSourceJacobianData[index + 2], kpSourceJacobianData[index + 3]]
        ];
        const jd = [
            [kpDrivingJacobianData[index], kpDrivingJacobianData[index + 1]],
            [kpDrivingJacobianData[index + 2], kpDrivingJacobianData[index + 3]]
        ];
        const jdi = [
            [kpDrivingInitialJacobianData[index], kpDrivingInitialJacobianData[index + 1]],
            [kpDrivingInitialJacobianData[index + 2], kpDrivingInitialJacobianData[index + 3]]
        ];

        // Compute inverse of jdi
        const jdiInv = math.inv(jdi);

        // Compute jacobian_diff = jd @ jdi_inv
        const jacobianDiff = math.multiply(jd, jdiInv);

        // Compute kpNewJacobian = jacobian_diff @ js
        const kpNewJacobian = math.multiply(jacobianDiff, js);

        // Flatten and store in kpJacobianNormalizedData
        kpJacobianNormalizedData[index] = kpNewJacobian[0][0];
        kpJacobianNormalizedData[index + 1] = kpNewJacobian[0][1];
        kpJacobianNormalizedData[index + 2] = kpNewJacobian[1][0];
        kpJacobianNormalizedData[index + 3] = kpNewJacobian[1][1];
    }

    return kpJacobianNormalizedData;
}
