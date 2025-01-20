import { YoutubeTranscript } from 'youtube-transcript';
import OpenAI from "openai";
import dotenv from "dotenv";
import fs from 'fs';
import path from 'path';
import { argv } from 'process';
import { fileURLToPath } from 'url';
import { zodResponseFormat } from "openai/helpers/zod";
import { z } from "zod";


dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const openai = new OpenAI({
    apiKey: process.env['OPENAI_API_KEY'], // This is the default and can be omitted
});

const forceFreshRun = argv.includes('--fresh');

// Ensure the directory exists
const ensureDirectoryExistence = (filePath) => {
    const dirname = path.dirname(filePath);
    if (!fs.existsSync(dirname)) {
        fs.mkdirSync(dirname, { recursive: true });
    }
};

async function fetchTranscriptJson(url) {
    const transcriptJsonFilePath = path.join(__dirname, 'out/transcript.json');
    ensureDirectoryExistence(transcriptJsonFilePath);
    if (!forceFreshRun && fs.existsSync(transcriptJsonFilePath)) {
        return JSON.parse(fs.readFileSync(transcriptJsonFilePath, 'utf-8'));
    }

    const transcriptObject = await YoutubeTranscript.fetchTranscript(url);
    fs.writeFileSync(transcriptJsonFilePath, JSON.stringify(transcriptObject, null, 2));

    return transcriptObject;
}

async function extractTranscriptText(transcriptObject) {
    const transcriptTextFilePath = path.join(__dirname, 'out/transcript.txt');
    ensureDirectoryExistence(transcriptTextFilePath);
    if (!forceFreshRun && fs.existsSync(transcriptTextFilePath)) {
        return fs.readFileSync(transcriptTextFilePath, 'utf-8');
    }

    const transcriptText = transcriptObject.map(entry => entry.text).join(' ');

    fs.writeFileSync(transcriptTextFilePath, transcriptText);

    return transcriptText;
}

async function cleanTranscript(transcriptText) {
    const cleanedTranscriptFilePath = path.join(__dirname, 'out/cleaned_transcript.txt');
    ensureDirectoryExistence(cleanedTranscriptFilePath);
    if (!forceFreshRun && fs.existsSync(cleanedTranscriptFilePath)) {
        return fs.readFileSync(cleanedTranscriptFilePath, 'utf-8');
    }

    const cleanupPrompt = `
    The youtube transcript provided is in its raw form as a string of words parsed from spoken words on a video.

    add in the proper grammar, punctuation, spelling, etc.
    the goal is to remain as close to verbatim as possible, while cleaning up punctuation.
    use simple unicode characters only, no special characters like m-dashes or open/close quotations.
    `;

    const cleanupResponse = await openai.chat.completions.create({
        messages: [
            { role: 'system', content: cleanupPrompt },
            { role: 'user', content: transcriptText },
        ],
        model: 'gpt-4o-mini', //dumbfast model for transcript cleanup
        temperature: 0.0,
    });

    const cleanedUpTranscriptText = cleanupResponse.choices[0].message.content;
    fs.writeFileSync(cleanedTranscriptFilePath, cleanedUpTranscriptText);
    return cleanedUpTranscriptText;
}

async function digestTranscript(transcriptText) {
    const digestFilepath = path.join(__dirname, 'out/transcript_digest.json');
    ensureDirectoryExistence(digestFilepath);
    if (!forceFreshRun && fs.existsSync(digestFilepath)) {
        return JSON.parse(fs.readFileSync(digestFilepath, 'utf-8'));
    }

    const digestionPrompt = `
You are an expert summarizer and analyst. 
Your task is to read the attached transcript and provide various summaries.
More details can be found in the output schema provided. 
Use simple unicode characters only, no special characters like m-dashes or open/close quotations.
`

    const transcriptDigest = z.object({
        page_summary: z.string().describe("A concise but detailed short-form notes document summarizing the transcript, keeping the length of these notes between half a page and two pages. Uses a standard markdown document format (starting with a # heading), prioritizing concise bulleted lists of notes over full paragraphs to get more complete coverage. Does not include quotes, keywords, or topic lists, only an simple, structured summary of the content."),
        paragraph_summary: z.string().describe("A concise summary of the transcript, at most a single paragraph."),
        sentence_summary: z.string().describe("An extremely concise summary of the transcript, at most a single sentence."),
        topics: z.array(z.string()).describe("An array of the broad, top-level general-focused themes or subjects discussed in the transcript. These topics should capture the overarching areas of interest or inquiry, providing users with an overview of the primary subjects covered. They should reflect the central themes in the content, offering a high-level understanding of the video."),
        keywords: z.array(z.string()).describe("An array of specific terms or phrases that are significant within the field(s) discussed in the transcript, akin to academic or well-established SEO keywords. These keywords should be precise and widely recognized within the relevant field or domain, aiding in search and discovery of related content. They should serve as effective search terms that encapsulate the detailed content discussed."),
        concepts: z.array(z.string()).describe("An array of educationally-focused ideas or principles that are explored within the transcript. These concepts should aim to represent the underlying notions or theories presented, providing insight into the key educational elements discussed. They should facilitate a deeper understanding of the content by highlighting the critical ideas conveyed in the video."),
        pull_quotes: z.array(z.string()).describe("An array of significant, memorable, or punchy quotes (best if all three!) that communicate core ideas or illustrate points, extracted VERBATIM from the transcript. (with the exception that the audio was highly compressed, so adjusting for obvious errors in transcription is acceptable."),
    }).strict();

    const completion = await openai.beta.chat.completions.parse({
        messages: [
            { role: "system", content: digestionPrompt },
            { role: "user", content: transcriptText },
        ],
        model: "gpt-4o", //midtier model for summarizations
        temperature: 0.0,
        response_format: zodResponseFormat(transcriptDigest, "digest"),
    });

    const digest = completion.choices[0].message.parsed;
    fs.writeFileSync(digestFilepath, JSON.stringify(digest, null, 2));
    return digest;
}

async function extractTimestampedUtterances(transcriptObject) {
    const timestampedUtterancesFilepath = path.join(__dirname, 'out/timestamped_utterances.txt');
    ensureDirectoryExistence(timestampedUtterancesFilepath);
    if (!forceFreshRun && fs.existsSync(timestampedUtterancesFilepath)) {
        return JSON.parse(fs.readFileSync(timestampedUtterancesFilepath, 'utf-8'));
    }

    const utterances = transcriptObject.map(entry => {
            const offsetInSeconds = entry.offset;

            const minutes = Math.floor(offsetInSeconds / 60);
            const seconds = Math.floor(offsetInSeconds % 60); // Use Math.floor to remove decimals

            const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            return `${formattedTime} ${entry.text}`;
        }).join('\n');

    fs.writeFileSync(timestampedUtterancesFilepath, utterances);
    return utterances;
}

async function extractChapters(transcriptDigest, timestampedUtterances, videoID) {
    const chaptersFilepath = path.join(__dirname, 'out/chapters.json');
    ensureDirectoryExistence(chaptersFilepath);
    if (!forceFreshRun && fs.existsSync(chaptersFilepath)) {
        return JSON.parse(fs.readFileSync(chaptersFilepath, 'utf-8'));
    }

    const chapterExtractionPrompt = `
You are an expert YouTube content editor tasked with creating chapter titles for a video based on the attached transcript.
Follow the rules closely, but aim for natural and engaging chapter titles.
`

    const chapterSchema = z.object({
        chapters: z.array(
            z.object({
                name: z.string().describe("name of chapter"),
                timestamp: z.string().describe("timestamp of format 00:00"),
                url: z.string().describe("url to the video with the timestamp"),
            })
        ).describe("An array of chapter titles presented in-order that could be used to break the transcript into sections of a youtube video. These should be concise and descriptive, providing a clear idea of what content is covered in each section of the video. Timestamps will be added at a later step. Must start from 00:00 and be listed in ascending order, minimum of 3, and minimum duration of 10 seconds between.")
    }).describe("Schema for chapters");

    const completion = await openai.beta.chat.completions.parse({
        messages: [
            { role: "system", content: chapterExtractionPrompt },
            { role: "user", content: transcriptDigest.toString() },
            { role: "user", content: timestampedUtterances.toString() },
            { role: "user", content: "youtube video ID: " + videoID}
        ],
        model: "gpt-4o", //midtier model for summarizations
        temperature: 0.0,
        response_format: zodResponseFormat(chapterSchema, "digest"),
    })

    const extractedChapters = completion.choices[0].message.parsed;

    extractedChapters["descriptionTextBlob"] = extractedChapters.chapters.map(chapter => chapter.timestamp + " " + chapter.name).join('\n').toString();

    fs.writeFileSync(chaptersFilepath, JSON.stringify(extractedChapters, null, 2));
    return extractedChapters;
}

async function main() {
    const url = 'https://youtu.be/F4FNNmuAq74';
    const videoID = url.split('v=')[1];
    const transcriptObject = await fetchTranscriptJson(url);
    console.log("Transcript JSON fetched:", transcriptObject);

    const transcriptText = await extractTranscriptText(transcriptObject);
    console.log("Transcript fetched:", transcriptText);

    const cleanedUpTranscriptText = await cleanTranscript(transcriptText);
    console.log("Cleaned Transcript:", cleanedUpTranscriptText);

    const transcriptDigest = await digestTranscript(cleanedUpTranscriptText);
    console.log("Transcript Digest:", transcriptDigest);

    const timestampedUtterances = await extractTimestampedUtterances(transcriptObject);
    console.log("Timestamped Utterances Extracted:", timestampedUtterances);

    const chapters = await extractChapters(transcriptDigest, timestampedUtterances, videoID);
    console.log("Chapters:", chapters);

    console.log("Stats:")
    console.log("original: " + transcriptText.length + " chars");
    console.log("cleaned: " + cleanedUpTranscriptText.length + " chars");
}


main().catch(console.error);